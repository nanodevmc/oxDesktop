use std::env;
use std::fs::OpenOptions;
use std::io::Write;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use aes::Aes256;
use ctr::cipher::{KeyIvInit, StreamCipher};
use ctr::Ctr128BE;
use futures_util::{SinkExt, StreamExt};
use rand::RngCore;
use sha2::{Digest, Sha256};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::Mutex;
use tokio_tungstenite::tungstenite::Message;

type Aes256Ctr = Ctr128BE<Aes256>;

const PROTO_TAG_ABRIDGED: [u8; 4] = [0xef, 0xef, 0xef, 0xef];
const PROTO_TAG_INTERMEDIATE: [u8; 4] = [0xee, 0xee, 0xee, 0xee];
const PROTO_TAG_SECURE: [u8; 4] = [0xdd, 0xdd, 0xdd, 0xdd];

#[derive(Clone)]
struct Logger {
    log_file: Option<PathBuf>,
    lock: Arc<Mutex<()>>,
}

impl Logger {
    fn new(log_file: Option<PathBuf>) -> Self {
        Self {
            log_file,
            lock: Arc::new(Mutex::new(())),
        }
    }

    async fn log(&self, msg: &str) {
        let ts = chrono_or_now();
        let line = format!("{}  INFO   oxWsProxy: {}\n", ts, msg);
        print!("{}", line);
        if let Some(ref path) = self.log_file {
            let _guard = self.lock.lock().await;
            if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
                let _ = f.write_all(line.as_bytes());
            }
        }
    }

    async fn warn(&self, msg: &str) {
        let ts = chrono_or_now();
        let line = format!("{}  WARN   oxWsProxy: {}\n", ts, msg);
        eprint!("{}", line);
        if let Some(ref path) = self.log_file {
            let _guard = self.lock.lock().await;
            if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
                let _ = f.write_all(line.as_bytes());
            }
        }
    }
}

fn chrono_or_now() -> String {
    // Generate simple HH:MM:SS timestamp using system time
    let dur = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    let secs = dur.as_secs() % 86400;
    let hours = (secs / 3600) % 24;
    let mins = (secs % 3600) / 60;
    let s = secs % 60;
    format!("{:02}:{:02}:{:02}", hours, mins, s)
}

fn decode_cf_domains() -> Vec<String> {
    const ENC: &[&str] = &[
        "virkgj.com", "vmmzovy.com", "mkuosckvso.com", "zaewayzmplad.com", "twdmbzcm.com",
        "awzwsldi.com", "clngqrflngqin.com", "tjacxbqtj.com", "bxaxtxmrw.com", "dmohrsgmohcrwb.com",
        "vwbmtmoi.com", "khgrre.com", "ulihssf.com", "tmhqsdqmfpmk.com", "xwuwoqbm.com",
        "orgcnunpj.com", "zhkuldz.com", "zypoljnslxa.com", "efabnxaowuzs.com", "zaftuzsftqdq.com",
    ];
    let suffix = ".co.uk";
    ENC.iter()
        .map(|s| {
            if let Some(prefix) = s.strip_suffix(".com") {
                let n = prefix.chars().filter(|c| c.is_ascii_alphabetic()).count() as u8;
                let mut decoded = String::new();
                for c in prefix.chars() {
                    if c.is_ascii_alphabetic() {
                        let base = if c.is_ascii_lowercase() { b'a' } else { b'A' };
                        let shifted = (c as u8 - base + 26 - (n % 26)) % 26 + base;
                        decoded.push(shifted as char);
                    } else {
                        decoded.push(c);
                    }
                }
                decoded.push_str(suffix);
                decoded
            } else {
                s.to_string()
            }
        })
        .collect()
}

#[cfg(windows)]
mod watchdog {
    type HANDLE = *mut std::ffi::c_void;
    type DWORD = u32;
    type BOOL = i32;

    const SYNCHRONIZE: DWORD = 0x00100000;
    const INFINITE: DWORD = 0xFFFFFFFF;

    extern "system" {
        fn OpenProcess(dwDesiredAccess: DWORD, bInheritHandle: BOOL, dwProcessId: DWORD) -> HANDLE;
        fn WaitForSingleObject(hHandle: HANDLE, dwMilliseconds: DWORD) -> DWORD;
        fn CloseHandle(hObject: HANDLE) -> BOOL;
    }

    pub fn start_watchdog(pid: u32) {
        std::thread::spawn(move || unsafe {
            let handle = OpenProcess(SYNCHRONIZE, 0, pid);
            if !handle.is_null() {
                WaitForSingleObject(handle, INFINITE);
                CloseHandle(handle);
                std::process::exit(0);
            }
        });
    }
}

#[cfg(not(windows))]
mod watchdog {
    extern "C" {
        fn kill(pid: i32, sig: i32) -> i32;
    }

    pub fn start_watchdog(pid: u32) {
        std::thread::spawn(move || loop {
            std::thread::sleep(std::time::Duration::from_secs(2));
            unsafe {
                if kill(pid as i32, 0) != 0 {
                    std::process::exit(0);
                }
            }
        });
    }
}

struct MsgSplitter {
    proto: [u8; 4],
    cipher_buf: Vec<u8>,
    plain_buf: Vec<u8>,
}

impl MsgSplitter {
    fn new(proto: [u8; 4]) -> Self {
        Self {
            proto,
            cipher_buf: Vec::new(),
            plain_buf: Vec::new(),
        }
    }

    fn split(&mut self, chunk: &[u8], plain: &[u8]) -> Vec<Vec<u8>> {
        self.cipher_buf.extend_from_slice(chunk);
        self.plain_buf.extend_from_slice(plain);

        let mut parts = Vec::new();
        let mut offset = 0;

        while offset < self.cipher_buf.len() {
            let avail = self.cipher_buf.len() - offset;
            let packet_len = match self.next_packet_len(offset, avail) {
                Some(len) if len > 0 => len,
                _ => break,
            };

            parts.push(self.cipher_buf[offset..offset + packet_len].to_vec());
            offset += packet_len;
        }

        if offset > 0 {
            self.cipher_buf.drain(..offset);
            self.plain_buf.drain(..offset);
        }

        parts
    }

    fn next_packet_len(&self, offset: usize, avail: usize) -> Option<usize> {
        if self.proto == PROTO_TAG_ABRIDGED {
            if avail < 1 {
                return None;
            }
            let first = self.plain_buf[offset];
            if first == 0x7F || first == 0xFF {
                if avail < 4 {
                    return None;
                }
                let len = u32::from_le_bytes([
                    self.plain_buf[offset + 1],
                    self.plain_buf[offset + 2],
                    self.plain_buf[offset + 3],
                    0,
                ]) as usize
                    * 4;
                Some(4 + len)
            } else {
                let len = ((first & 0x7F) as usize) * 4;
                Some(1 + len)
            }
        } else {
            // Intermediate & Secure Intermediate (padded)
            if avail < 4 {
                return None;
            }
            let len = (u32::from_le_bytes([
                self.plain_buf[offset],
                self.plain_buf[offset + 1],
                self.plain_buf[offset + 2],
                self.plain_buf[offset + 3],
            ]) & 0x7FFFFFFF) as usize;
            Some(4 + len)
        }
    }
}

fn generate_relay_init(proto_tag: [u8; 4], dc_idx: i16) -> (Vec<u8>, Aes256Ctr, Aes256Ctr) {
    let mut rng = rand::thread_rng();
    let mut rnd = [0u8; 64];

    loop {
        rng.fill_bytes(&mut rnd);
        let first = rnd[0];
        if first == 0xEF {
            continue;
        }
        let head = &rnd[0..4];
        if head == b"HEAD"
            || head == b"POST"
            || head == b"GET "
            || head == &PROTO_TAG_INTERMEDIATE
            || head == &PROTO_TAG_SECURE
            || head == [0x16, 0x03, 0x01, 0x02]
            || head == b"OPTI"
        {
            continue;
        }
        if &rnd[4..8] == &[0, 0, 0, 0] {
            continue;
        }
        break;
    }

    let relay_enc_key = rnd[8..40].to_vec();
    let relay_enc_iv = rnd[40..56].to_vec();

    let mut relay_dec_prekey_iv = rnd[8..56].to_vec();
    relay_dec_prekey_iv.reverse();
    let relay_dec_key = relay_dec_prekey_iv[0..32].to_vec();
    let relay_dec_iv = relay_dec_prekey_iv[32..48].to_vec();

    let mut tg_enc =
        Aes256Ctr::new_from_slices(&relay_enc_key, &relay_enc_iv).expect("invalid tg_enc");
    let tg_dec =
        Aes256Ctr::new_from_slices(&relay_dec_key, &relay_dec_iv).expect("invalid tg_dec");

    let mut encrypted_full = rnd;
    tg_enc.apply_keystream(&mut encrypted_full);

    let keystream_tail: Vec<u8> = (56..64).map(|i| encrypted_full[i] ^ rnd[i]).collect();
    let dc_bytes = dc_idx.to_le_bytes();
    let mut rnd2 = [0u8; 2];
    rng.fill_bytes(&mut rnd2);

    let tail_plain = [
        proto_tag[0],
        proto_tag[1],
        proto_tag[2],
        proto_tag[3],
        dc_bytes[0],
        dc_bytes[1],
        rnd2[0],
        rnd2[1],
    ];

    let mut result = rnd.to_vec();
    for i in 0..8 {
        result[56 + i] = tail_plain[i] ^ keystream_tail[i];
    }

    (result, tg_enc, tg_dec)
}

async fn handle_client(
    mut client_socket: TcpStream,
    peer: SocketAddr,
    secret: Arc<Vec<u8>>,
    cf_domains: Arc<Vec<String>>,
    logger: Logger,
) {
    let mut handshake = [0u8; 64];
    if let Err(_) = client_socket.read_exact(&mut handshake).await {
        return;
    }

    let dec_prekey = &handshake[8..40];
    let dec_iv = &handshake[40..56];

    let mut hasher = Sha256::new();
    hasher.update(dec_prekey);
    hasher.update(&*secret);
    let dec_key = hasher.finalize();

    let mut decryptor =
        Aes256Ctr::new_from_slices(&dec_key, dec_iv).expect("invalid decryptor key/iv");
    let mut decrypted = handshake;
    decryptor.apply_keystream(&mut decrypted);

    let proto_tag: [u8; 4] = [
        decrypted[56],
        decrypted[57],
        decrypted[58],
        decrypted[59],
    ];
    if proto_tag != PROTO_TAG_ABRIDGED
        && proto_tag != PROTO_TAG_INTERMEDIATE
        && proto_tag != PROTO_TAG_SECURE
    {
        logger.warn(&format!("[{}] bad handshake protocol tag", peer)).await;
        return;
    }

    let dc_idx = i16::from_le_bytes([decrypted[60], decrypted[61]]);
    let dc = dc_idx.unsigned_abs() as u8;
    let is_media = dc_idx < 0;
    let actual_dc = if dc == 0 || dc > 5 && dc != 203 { 2 } else { dc };

    // Set up client ciphers
    let mut clt_dec =
        Aes256Ctr::new_from_slices(&dec_key, dec_iv).expect("invalid clt_dec");
    clt_dec.apply_keystream(&mut [0u8; 64]); // advance past handshake

    let mut clt_enc_prekey_iv = handshake[8..56].to_vec();
    clt_enc_prekey_iv.reverse();
    let mut enc_hasher = Sha256::new();
    enc_hasher.update(&clt_enc_prekey_iv[0..32]);
    enc_hasher.update(&*secret);
    let clt_enc_key = enc_hasher.finalize();
    let clt_enc_iv = &clt_enc_prekey_iv[32..48];

    let mut clt_enc =
        Aes256Ctr::new_from_slices(&clt_enc_key, clt_enc_iv).expect("invalid clt_enc");

    let (relay_init, mut tg_enc, mut tg_dec) = generate_relay_init(proto_tag, dc_idx);

    logger
        .log(&format!(
            "[{}] Handshake OK: DC{}{} proto=0x{:02X}{:02X}{:02X}{:02X}",
            peer, actual_dc, if is_media { "m" } else { "" },
            proto_tag[0], proto_tag[1], proto_tag[2], proto_tag[3]
        ))
        .await;

    // Connect to Telegram WebSocket endpoint
    let mut ws_stream = None;
    let direct_url = format!("wss://kws{}.web.telegram.org/apiws", actual_dc);
    let direct_media_url = format!("wss://kws{}-1.web.telegram.org/apiws", actual_dc);
    let candidate_direct = if is_media {
        vec![direct_media_url, direct_url]
    } else {
        vec![direct_url]
    };

    for url in candidate_direct {
        match tokio::time::timeout(
            Duration::from_secs(5),
            tokio_tungstenite::connect_async(&url),
        )
        .await
        {
            Ok(Ok((ws, _))) => {
                logger.log(&format!("[{}] Connected to direct WS: {}", peer, url)).await;
                ws_stream = Some(ws);
                break;
            }
            _ => continue,
        }
    }

    // Fallback to Cloudflare workers if direct fails
    if ws_stream.is_none() {
        for cf_domain in cf_domains.iter() {
            let cf_url = format!("wss://kws{}.{}/apiws", actual_dc, cf_domain);
            match tokio::time::timeout(
                Duration::from_secs(5),
                tokio_tungstenite::connect_async(&cf_url),
            )
            .await
            {
                Ok(Ok((ws, _))) => {
                    logger
                        .log(&format!("[{}] Connected to CF fallback: {}", peer, cf_url))
                        .await;
                    ws_stream = Some(ws);
                    break;
                }
                _ => continue,
            }
        }
    }

    let mut ws = match ws_stream {
        Some(w) => w,
        None => {
            logger
                .warn(&format!("[{}] Failed to connect to any WS backend for DC{}", peer, actual_dc))
                .await;
            return;
        }
    };

    // Send initial relay frame
    if let Err(e) = ws.send(Message::Binary(relay_init.into())).await {
        logger.warn(&format!("[{}] Failed to send relay init: {}", peer, e)).await;
        return;
    }

    let (mut ws_sink, mut ws_src) = ws.split();
    let (mut client_reader, mut client_writer) = client_socket.into_split();

    let mut splitter = MsgSplitter::new(proto_tag);

    let client_to_ws = async {
        let mut buf = vec![0u8; 65536];
        loop {
            let n = match client_reader.read(&mut buf).await {
                Ok(0) => break,
                Ok(n) => n,
                Err(_) => break,
            };

            let chunk = &buf[..n];
            let mut plain = chunk.to_vec();
            clt_dec.apply_keystream(&mut plain);

            let mut cipher_chunk = plain.clone();
            tg_enc.apply_keystream(&mut cipher_chunk);

            let parts = splitter.split(&cipher_chunk, &plain);
            if parts.is_empty() {
                if let Err(_) = ws_sink.send(Message::Binary(cipher_chunk.into())).await {
                    break;
                }
            } else {
                for part in parts {
                    if let Err(_) = ws_sink.send(Message::Binary(part.into())).await {
                        return;
                    }
                }
            }
        }
    };

    let ws_to_client = async {
        while let Some(msg_res) = ws_src.next().await {
            let msg = match msg_res {
                Ok(m) => m,
                Err(_) => break,
            };

            if let Message::Binary(data) = msg {
                let mut data_vec = data.to_vec();
                tg_dec.apply_keystream(&mut data_vec);
                clt_enc.apply_keystream(&mut data_vec);

                if let Err(_) = client_writer.write_all(&data_vec).await {
                    break;
                }
            }
        }
    };

    tokio::select! {
        _ = client_to_ws => {},
        _ = ws_to_client => {},
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let mut port: u16 = 1443;
    let mut secret_hex = String::new();
    let mut parent_pid: Option<u32> = None;
    let mut log_file: Option<PathBuf> = None;

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--port" => {
                if i + 1 < args.len() {
                    port = args[i + 1].parse().unwrap_or(1443);
                    i += 1;
                }
            }
            "--secret" => {
                if i + 1 < args.len() {
                    secret_hex = args[i + 1].clone();
                    i += 1;
                }
            }
            "--parent-pid" => {
                if i + 1 < args.len() {
                    parent_pid = args[i + 1].parse().ok();
                    i += 1;
                }
            }
            "--log-file" => {
                if i + 1 < args.len() {
                    log_file = Some(PathBuf::from(&args[i + 1]));
                    i += 1;
                }
            }
            _ => {}
        }
        i += 1;
    }

    let secret = hex::decode(&secret_hex).unwrap_or_else(|_| vec![0u8; 16]);
    let secret = Arc::new(secret);
    let cf_domains = Arc::new(decode_cf_domains());
    let logger = Logger::new(log_file);

    if let Some(pid) = parent_pid {
        watchdog::start_watchdog(pid);
        logger.log(&format!("Attached to parent PID {}", pid)).await;
    }

    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let listener = match TcpListener::bind(addr).await {
        Ok(l) => l,
        Err(e) => {
            logger.warn(&format!("Failed to bind on {}: {}", addr, e)).await;
            return Err(e.into());
        }
    };

    logger
        .log(&format!("Native Rust oxWsProxy listening on http://{}", addr))
        .await;

    loop {
        match listener.accept().await {
            Ok((socket, peer)) => {
                let secret_clone = Arc::clone(&secret);
                let cf_clone = Arc::clone(&cf_domains);
                let logger_clone = logger.clone();
                tokio::spawn(async move {
                    handle_client(socket, peer, secret_clone, cf_clone, logger_clone).await;
                });
            }
            Err(e) => {
                logger.warn(&format!("Accept error: {}", e)).await;
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        }
    }
}
