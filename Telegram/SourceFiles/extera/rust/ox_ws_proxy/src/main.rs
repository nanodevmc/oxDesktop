use std::env;
use std::fs::OpenOptions;
use std::io::Write;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::time::Duration;

use aes::Aes256;
use ctr::cipher::{KeyIvInit, StreamCipher};
use ctr::Ctr128BE;
use futures_util::{SinkExt, StreamExt};
use rand::RngCore;
use rustls::client::danger::{HandshakeSignatureValid, ServerCertVerified, ServerCertVerifier};
use rustls_pki_types::{CertificateDer, ServerName, UnixTime};
use sha2::{Digest, Sha256};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{mpsc, Mutex};
use tokio_rustls::TlsConnector;
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::http::HeaderValue;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::{client_async, MaybeTlsStream, WebSocketStream};

type Aes256Ctr = Ctr128BE<Aes256>;

const PROTO_TAG_ABRIDGED: [u8; 4] = [0xef, 0xef, 0xef, 0xef];
const PROTO_TAG_INTERMEDIATE: [u8; 4] = [0xee, 0xee, 0xee, 0xee];
const PROTO_TAG_SECURE: [u8; 4] = [0xdd, 0xdd, 0xdd, 0xdd];
const WHITE_SNI_LIST: &[&str] = &["vk.com", "mail.ru", "ya.ru", "yandex.ru", "ok.ru"];

static CF_POOL_CURSOR: AtomicUsize = AtomicUsize::new(0);

fn get_dc_ips(dc: u8) -> &'static [&'static str] {
    match dc {
        1 => &[
            "149.154.175.50",
            "149.154.175.53",
            "149.154.174.100",
            "149.154.175.209",
            "149.154.167.220",
        ],
        2 => &[
            "149.154.167.50",
            "149.154.167.51",
            "149.154.167.99",
            "149.154.167.220",
        ],
        3 => &[
            "149.154.175.100",
            "149.154.174.100",
            "149.154.175.209",
            "149.154.167.220",
        ],
        4 => &[
            "149.154.167.91",
            "149.154.167.99",
            "149.154.167.220",
        ],
        5 => &[
            "91.108.56.130",
            "149.154.171.5",
            "149.154.170.100",
            "149.154.171.237",
            "149.154.170.96",
            "149.154.171.236",
            "149.154.167.220",
        ],
        _ => &[
            "149.154.167.220",
            "149.154.167.99",
            "149.154.175.53",
            "91.108.56.130",
        ],
    }
}

#[derive(Debug)]
struct NoVerifier;

impl ServerCertVerifier for NoVerifier {
    fn verify_server_cert(
        &self,
        _end_entity: &CertificateDer<'_>,
        _intermediates: &[CertificateDer<'_>],
        _server_name: &ServerName<'_>,
        _ocsp_response: &[u8],
        _now: UnixTime,
    ) -> Result<ServerCertVerified, rustls::Error> {
        Ok(ServerCertVerified::assertion())
    }

    fn verify_tls12_signature(
        &self,
        _message: &[u8],
        _cert: &CertificateDer<'_>,
        _dss: &rustls::DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, rustls::Error> {
        Ok(HandshakeSignatureValid::assertion())
    }

    fn verify_tls13_signature(
        &self,
        _message: &[u8],
        _cert: &CertificateDer<'_>,
        _dss: &rustls::DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, rustls::Error> {
        Ok(HandshakeSignatureValid::assertion())
    }

    fn supported_verify_schemes(&self) -> Vec<rustls::SignatureScheme> {
        rustls::crypto::ring::default_provider()
            .signature_verification_algorithms
            .supported_schemes()
    }
}

fn create_fronting_tls_connector() -> TlsConnector {
    let config = rustls::ClientConfig::builder_with_provider(Arc::new(
        rustls::crypto::ring::default_provider(),
    ))
    .with_safe_default_protocol_versions()
    .expect("TLS protocol versions")
    .dangerous()
    .with_custom_certificate_verifier(Arc::new(NoVerifier))
    .with_no_client_auth();
    TlsConnector::from(Arc::new(config))
}

async fn connect_fronted_ws(
    dc_ip: &str,
    target_host: &str,
    sni: &str,
    connector: &TlsConnector,
) -> Result<WebSocketStream<MaybeTlsStream<TcpStream>>, Box<dyn std::error::Error + Send + Sync>> {
    let tcp = TcpStream::connect(format!("{}:443", dc_ip)).await?;
    let _ = tcp.set_nodelay(true);
    let server_name = ServerName::try_from(sni.to_string())?;
    let tls = connector.connect(server_name, tcp).await?;
    let stream = MaybeTlsStream::Rustls(tls);

    let uri = format!("wss://{}/apiws", target_host);
    let mut request = uri.into_client_request()?;
    request.headers_mut().insert(
        "Host",
        HeaderValue::from_str(target_host)?,
    );
    request.headers_mut().insert(
        "Sec-WebSocket-Protocol",
        HeaderValue::from_static("binary"),
    );

    let (ws, _resp) = client_async(request, stream).await?;
    Ok(ws)
}

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
                Some(len) if len > 0 && avail >= len => len,
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
                let len = (u32::from_le_bytes([
                    self.plain_buf[offset + 1],
                    self.plain_buf[offset + 2],
                    self.plain_buf[offset + 3],
                    0,
                ]) as usize)
                    .checked_mul(4)?;
                let total_len = 4usize.checked_add(len)?;
                if avail < total_len {
                    return None;
                }
                Some(total_len)
            } else {
                let len = ((first & 0x7F) as usize) * 4;
                let total_len = 1usize.checked_add(len)?;
                if avail < total_len {
                    return None;
                }
                Some(total_len)
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
            let total_len = 4usize.checked_add(len)?;
            if avail < total_len {
                return None;
            }
            Some(total_len)
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

#[allow(dead_code)]
enum BackendStream {
    Ws(WebSocketStream<MaybeTlsStream<TcpStream>>),
    Tcp(TcpStream),
}

struct BackendConn {
    stream: BackendStream,
    desc: String,
}

struct AbortOnDrop(Vec<tokio::task::JoinHandle<()>>);

impl Drop for AbortOnDrop {
    fn drop(&mut self) {
        for handle in &self.0 {
            handle.abort();
        }
    }
}

async fn race_backend_connection(
    actual_dc: u8,
    ips: &'static [&'static str],
    candidate_hosts: &[String],
    cf_domains: Arc<Vec<String>>,
    tls_connector: Arc<TlsConnector>,
    logger: &Logger,
    peer: SocketAddr,
) -> Option<BackendConn> {
    let (tx, mut rx) = mpsc::channel::<BackendConn>(1);
    let mut guards = AbortOnDrop(Vec::new());
    let last_err: Arc<Mutex<Option<String>>> = Arc::new(Mutex::new(None));

    // 1. Parallel Direct WS probes
    for host in candidate_hosts {
        let tx = tx.clone();
        let last_err = last_err.clone();
        let direct_url = format!("wss://{}/apiws", host);
        let host_name = host.clone();
        guards.0.push(tokio::spawn(async move {
            if let Ok(mut req) = direct_url.into_client_request() {
                req.headers_mut().insert(
                    "Sec-WebSocket-Protocol",
                    HeaderValue::from_static("binary"),
                );
                match tokio::time::timeout(
                    Duration::from_millis(5000),
                    tokio_tungstenite::connect_async(req),
                )
                .await
                {
                    Ok(Ok((ws, _))) => {
                        let _ = tx.send(BackendConn {
                            stream: BackendStream::Ws(ws),
                            desc: format!("Direct WS ({})", host_name),
                        }).await;
                    }
                    Ok(Err(e)) => {
                        *last_err.lock().await = Some(format!("Direct WS ({}): {}", host_name, e));
                    }
                    Err(_) => {}
                }
            }
        }));
    }

    // 2. Parallel TLS Domain Fronting probes to DC IPs (using white-listed SNIs)
    let primary_target_host = candidate_hosts[0].clone();
    for (ip_idx, &ip) in ips.iter().enumerate() {
        for (sni_idx, &sni) in WHITE_SNI_LIST.iter().enumerate() {
            let connector = tls_connector.clone();
            let target_host = if ip_idx == 0 && sni_idx == 0 {
                primary_target_host.clone()
            } else {
                candidate_hosts[(ip_idx + sni_idx) % candidate_hosts.len()].clone()
            };
            let tx = tx.clone();
            guards.0.push(tokio::spawn(async move {
                if let Ok(Ok(ws)) = tokio::time::timeout(
                    Duration::from_millis(5000),
                    connect_fronted_ws(ip, &target_host, sni, &connector),
                )
                .await
                {
                    let _ = tx.send(BackendConn {
                        stream: BackendStream::Ws(ws),
                        desc: format!("Fronted WS ({}:443 via {})", ip, sni),
                    }).await;
                }
            }));
        }
    }

    // 3. Parallel Cloudflare Worker probes across full domain pool & DC IPs
    if !cf_domains.is_empty() && !ips.is_empty() {
        let start_offset = CF_POOL_CURSOR.fetch_add(1, Ordering::Relaxed) % cf_domains.len();
        for i in 0..cf_domains.len() {
            let cf_domain = cf_domains[(start_offset + i) % cf_domains.len()].clone();
            let target_ip = ips[i % ips.len()];
            let cf_url = format!("wss://{}/apiws?dst={}&dc={}", cf_domain, target_ip, actual_dc);
            let tx = tx.clone();
            guards.0.push(tokio::spawn(async move {
                tokio::time::sleep(Duration::from_millis(40)).await;
                if let Ok(mut req) = cf_url.into_client_request() {
                    req.headers_mut().insert(
                        "Sec-WebSocket-Protocol",
                        HeaderValue::from_static("binary"),
                    );
                    if let Ok(Ok((ws, _))) = tokio::time::timeout(
                        Duration::from_millis(6500),
                        tokio_tungstenite::connect_async(req),
                    )
                    .await
                    {
                        let _ = tx.send(BackendConn {
                            stream: BackendStream::Ws(ws),
                            desc: format!("CF Relay ({})", cf_domain),
                        }).await;
                    }
                }
            }));
        }
    }

    // 4. Parallel Direct MTProto TCP probes to DC IPs (ports 443, 80, 5222)
    for &ip in ips {
        for &port in &[443u16, 80u16, 5222u16] {
            let tx = tx.clone();
            let target_addr: Result<SocketAddr, _> = format!("{}:{}", ip, port).parse();
            if let Ok(addr) = target_addr {
                guards.0.push(tokio::spawn(async move {
                    if let Ok(Ok(stream)) = tokio::time::timeout(
                        Duration::from_millis(4500),
                        tokio::net::TcpStream::connect(addr),
                    )
                    .await
                    {
                        let _ = tx.send(BackendConn {
                            stream: BackendStream::Tcp(stream),
                            desc: format!("Direct MTProto TCP ({}:{})", ip, port),
                        }).await;
                    }
                }));
            }
        }
    }

    drop(tx);

    match tokio::time::timeout(Duration::from_millis(12000), rx.recv()).await {
        Ok(Some(backend)) => {
            logger
                .log(&format!("[{}] Connected via {} to DC{}", peer, backend.desc, actual_dc))
                .await;
            Some(backend)
        }
        _ => {
            if let Some(err) = last_err.lock().await.as_ref() {
                logger
                    .warn(&format!("[{}] Last backend error for DC{}: {}", peer, actual_dc, err))
                    .await;
            }
            None
        }
    }
}

fn is_http_method_prefix(buf: &[u8]) -> bool {
    const METHODS: &[&[u8]] = &[
        b"CONNECT ",
        b"GET ",
        b"POST ",
        b"HEAD ",
        b"PUT ",
        b"DELETE ",
        b"OPTIONS ",
    ];
    METHODS.iter().any(|m| buf.starts_with(m))
}

fn is_github_host(host: &str) -> bool {
    let lower = host.to_ascii_lowercase();
    lower.contains("github.com") || lower.contains("githubusercontent.com")
}

fn parse_host_port(authority: &str, default_port: u16) -> Option<(String, u16)> {
    let trimmed = authority.trim();
    if trimmed.is_empty() {
        return None;
    }
    if let Some(rest) = trimmed.strip_prefix('[') {
        let end = rest.find(']')?;
        let host = rest[..end].to_string();
        let after = &rest[end + 1..];
        let port = if let Some(p) = after.strip_prefix(':') {
            p.parse::<u16>().ok()?
        } else {
            default_port
        };
        return Some((host, port));
    }
    if let Some(colon) = trimmed.rfind(':') {
        let host = &trimmed[..colon];
        let port_str = &trimmed[colon + 1..];
        if !host.is_empty() && !port_str.is_empty() {
            if let Ok(port) = port_str.parse::<u16>() {
                return Some((host.to_string(), port));
            }
        }
    }
    Some((trimmed.to_string(), default_port))
}

async fn read_http_header(stream: &mut TcpStream) -> Option<(String, Vec<u8>)> {
    let mut buf = Vec::with_capacity(2048);
    let mut tmp = [0u8; 4096];
    loop {
        let n = match tokio::time::timeout(Duration::from_secs(10), stream.read(&mut tmp)).await {
            Ok(Ok(0)) | Ok(Err(_)) | Err(_) => return None,
            Ok(Ok(n)) => n,
        };
        buf.extend_from_slice(&tmp[..n]);
        if let Some(pos) = buf.windows(4).position(|w| w == b"\r\n\r\n") {
            let hdr = String::from_utf8_lossy(&buf[..pos]).into_owned();
            let excess = buf[pos + 4..].to_vec();
            return Some((hdr, excess));
        }
        if let Some(pos) = buf.windows(2).position(|w| w == b"\n\n") {
            let hdr = String::from_utf8_lossy(&buf[..pos]).into_owned();
            let excess = buf[pos + 2..].to_vec();
            return Some((hdr, excess));
        }
        if buf.len() >= 32768 {
            return None;
        }
    }
}

async fn handle_http_proxy(
    mut client_socket: TcpStream,
    peer: SocketAddr,
    listen_port: u16,
    tls_connector: Arc<TlsConnector>,
    logger: Logger,
) {
    let (header_text, excess) = match read_http_header(&mut client_socket).await {
        Some(res) => res,
        None => {
            let _ = client_socket
                .write_all(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
                .await;
            return;
        }
    };

    let mut lines = header_text.split('\n').map(|l| l.trim_end_matches('\r'));
    let req_line = match lines.next() {
        Some(l) => l,
        None => return,
    };
    let mut parts = req_line.split_whitespace();
    let method = match parts.next() {
        Some(m) => m,
        None => return,
    };
    let target = match parts.next() {
        Some(t) => t,
        None => return,
    };

    let raw_headers: Vec<&str> = lines.filter(|l| !l.is_empty()).collect();
    let host_header = raw_headers.iter().find_map(|line| {
        let (k, v) = line.split_once(':')?;
        if k.trim().eq_ignore_ascii_case("host") {
            Some(v.trim())
        } else {
            None
        }
    });

    if method.eq_ignore_ascii_case("CONNECT") {
        let (host, port) = match parse_host_port(target, 443) {
            Some(hp) => hp,
            None => {
                let _ = client_socket
                    .write_all(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
                    .await;
                return;
            }
        };
        if (host.eq_ignore_ascii_case("127.0.0.1") || host.eq_ignore_ascii_case("localhost"))
            && port == listen_port
        {
            let _ = client_socket
                .write_all(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
                .await;
            return;
        }

        let is_github = is_github_host(&host);
        logger
            .log(&format!(
                "[{}] HTTP CONNECT {}:{} ({})",
                peer,
                host,
                port,
                if is_github { "direct-github" } else { "tunnel" }
            ))
            .await;

        match tokio::time::timeout(
            Duration::from_secs(10),
            TcpStream::connect((host.as_str(), port)),
        )
        .await
        {
            Ok(Ok(mut upstream)) => {
                let _ = upstream.set_nodelay(true);
                if client_socket
                    .write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    .await
                    .is_err()
                {
                    return;
                }
                if !excess.is_empty() && upstream.write_all(&excess).await.is_err() {
                    return;
                }
                let _ = tokio::io::copy_bidirectional(&mut client_socket, &mut upstream).await;
            }
            _ => {
                logger
                    .warn(&format!("[{}] HTTP CONNECT failed for {}:{}", peer, host, port))
                    .await;
                let _ = client_socket
                    .write_all(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
                    .await;
            }
        }
        return;
    }

    let mut is_tls_from_header = false;
    for line in &raw_headers {
        if let Some((k, v)) = line.split_once(':') {
            let key = k.trim();
            if key.eq_ignore_ascii_case("x-ox-tls") && v.trim() == "1" {
                is_tls_from_header = true;
                continue;
            }
        }
    }

    let (is_tls, host, port, path) = if let Some(rest) = target.strip_prefix("https://") {
        let (auth, path) = match rest.find('/') {
            Some(idx) => (&rest[..idx], &rest[idx..]),
            None => (rest, "/"),
        };
        match parse_host_port(auth, 443) {
            Some((h, p)) => (true, h, p, path.to_string()),
            None => return,
        }
    } else if let Some(rest) = target.strip_prefix("http://") {
        let (auth, path) = match rest.find('/') {
            Some(idx) => (&rest[..idx], &rest[idx..]),
            None => (rest, "/"),
        };
        let def_port = if is_tls_from_header { 443 } else { 80 };
        match parse_host_port(auth, def_port) {
            Some((h, p)) => (is_tls_from_header, h, if is_tls_from_header && p == 80 { 443 } else { p }, path.to_string()),
            None => return,
        }
    } else {
        let def_port = if is_tls_from_header { 443 } else { 80 };
        match host_header.and_then(|h| parse_host_port(h, def_port)) {
            Some((h, p))
                if !(h.eq_ignore_ascii_case("127.0.0.1") || h.eq_ignore_ascii_case("localhost"))
                    || p != listen_port =>
            {
                (is_tls_from_header, h, if is_tls_from_header && p == 80 { 443 } else { p }, target.to_string())
            }
            _ => {
                let _ = client_socket
                    .write_all(
                        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\nContent-Length: 13\r\n\r\noxWsProxy OK\n",
                    )
                    .await;
                return;
            }
        }
    };

    if (host.eq_ignore_ascii_case("127.0.0.1") || host.eq_ignore_ascii_case("localhost"))
        && port == listen_port
    {
        let _ = client_socket
            .write_all(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\nContent-Length: 13\r\n\r\noxWsProxy OK\n",
            )
            .await;
        return;
    }

    let mut rebuilt = format!("{} {} HTTP/1.1\r\n", method, path);
    let mut has_host = false;
    for line in &raw_headers {
        if let Some((k, _)) = line.split_once(':') {
            let key = k.trim();
            if key.eq_ignore_ascii_case("proxy-connection")
                || key.eq_ignore_ascii_case("connection")
                || key.eq_ignore_ascii_case("x-ox-tls")
            {
                continue;
            }
            if key.eq_ignore_ascii_case("host") {
                has_host = true;
            }
        }
        rebuilt.push_str(line);
        rebuilt.push_str("\r\n");
    }
    if !has_host {
        rebuilt.push_str(&format!("Host: {}\r\n", host));
    }
    rebuilt.push_str("Connection: close\r\n\r\n");

    let is_github = is_github_host(&host);
    logger
        .log(&format!(
            "[{}] HTTP {} {}://{}:{}{}",
            peer,
            method,
            if is_tls { "https" } else { "http" },
            host,
            port,
            path
        ))
        .await;

    if !is_tls {
        match tokio::time::timeout(
            Duration::from_secs(10),
            TcpStream::connect((host.as_str(), port)),
        )
        .await
        {
            Ok(Ok(mut upstream)) => {
                let _ = upstream.set_nodelay(true);
                if upstream.write_all(rebuilt.as_bytes()).await.is_err() {
                    return;
                }
                if !excess.is_empty() && upstream.write_all(&excess).await.is_err() {
                    return;
                }
                let _ = tokio::io::copy_bidirectional(&mut client_socket, &mut upstream).await;
            }
            _ => {
                let _ = client_socket
                    .write_all(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
                    .await;
            }
        }
        return;
    }

    let sni_candidates: Vec<&str> = if is_github {
        vec![host.as_str()]
    } else {
        let mut list = vec![host.as_str()];
        list.extend_from_slice(WHITE_SNI_LIST);
        list
    };

    for sni in sni_candidates {
        let tcp = match tokio::time::timeout(
            Duration::from_secs(8),
            TcpStream::connect((host.as_str(), port)),
        )
        .await
        {
            Ok(Ok(s)) => s,
            _ => continue,
        };
        let _ = tcp.set_nodelay(true);
        let server_name = match ServerName::try_from(sni.to_string()) {
            Ok(sn) => sn,
            Err(_) => continue,
        };
        if let Ok(Ok(mut tls)) = tokio::time::timeout(
            Duration::from_secs(8),
            tls_connector.connect(server_name, tcp),
        )
        .await
        {
            if tls.write_all(rebuilt.as_bytes()).await.is_err() {
                return;
            }
            if !excess.is_empty() && tls.write_all(&excess).await.is_err() {
                return;
            }
            let _ = tokio::io::copy_bidirectional(&mut client_socket, &mut tls).await;
            return;
        }
    }

    let _ = client_socket
        .write_all(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
        .await;
}

async fn handle_client(
    mut client_socket: TcpStream,
    peer: SocketAddr,
    listen_port: u16,
    secret: Arc<Vec<u8>>,
    cf_domains: Arc<Vec<String>>,
    tls_connector: Arc<TlsConnector>,
    logger: Logger,
) {
    let mut peek_buf = [0u8; 64];
    let peek_n = match client_socket.peek(&mut peek_buf).await {
        Ok(0) => return,
        Ok(n) => n,
        Err(_) => return,
    };
    if peek_n < 8 && b"CONNECT ".starts_with(&peek_buf[..peek_n]) {
        tokio::time::sleep(Duration::from_millis(10)).await;
        if let Ok(n) = client_socket.peek(&mut peek_buf).await {
            if is_http_method_prefix(&peek_buf[..n]) {
                handle_http_proxy(client_socket, peer, listen_port, tls_connector, logger).await;
                return;
            }
        }
    } else if is_http_method_prefix(&peek_buf[..peek_n]) {
        handle_http_proxy(client_socket, peer, listen_port, tls_connector, logger).await;
        return;
    }

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
    let actual_dc = if (1..=5).contains(&dc) { dc } else { 2 };

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

    // Connect to Telegram backend
    let ips = get_dc_ips(actual_dc);

    let candidate_hosts: Vec<String> = match actual_dc {
        1 => if is_media {
            vec![
                "pluto-1.web.telegram.org".to_string(),
                "kws1-1.web.telegram.org".to_string(),
                "kws1.web.telegram.org".to_string(),
            ]
        } else {
            vec![
                "kws1.web.telegram.org".to_string(),
                "pluto-1.web.telegram.org".to_string(),
                "kws1-1.web.telegram.org".to_string(),
            ]
        },
        2 => if is_media {
            vec![
                "venus-1.web.telegram.org".to_string(),
                "kws2-1.web.telegram.org".to_string(),
                "kws2.web.telegram.org".to_string(),
            ]
        } else {
            vec![
                "kws2.web.telegram.org".to_string(),
                "venus-1.web.telegram.org".to_string(),
                "kws2-1.web.telegram.org".to_string(),
            ]
        },
        3 => if is_media {
            vec![
                "aurora-1.web.telegram.org".to_string(),
                "kws3-1.web.telegram.org".to_string(),
                "kws3.web.telegram.org".to_string(),
            ]
        } else {
            vec![
                "kws3.web.telegram.org".to_string(),
                "aurora-1.web.telegram.org".to_string(),
                "kws3-1.web.telegram.org".to_string(),
            ]
        },
        4 => if is_media {
            vec![
                "vesta-1.web.telegram.org".to_string(),
                "kws4-1.web.telegram.org".to_string(),
                "kws4.web.telegram.org".to_string(),
            ]
        } else {
            vec![
                "kws4.web.telegram.org".to_string(),
                "vesta-1.web.telegram.org".to_string(),
                "kws4-1.web.telegram.org".to_string(),
            ]
        },
        5 => if is_media {
            vec![
                "flora-1.web.telegram.org".to_string(),
                "kws5-1.web.telegram.org".to_string(),
                "kws5.web.telegram.org".to_string(),
            ]
        } else {
            vec![
                "kws5.web.telegram.org".to_string(),
                "flora-1.web.telegram.org".to_string(),
                "kws5-1.web.telegram.org".to_string(),
            ]
        },
        _ => vec![format!("kws{}.web.telegram.org", actual_dc)],
    };

    let backend = match race_backend_connection(
        actual_dc,
        ips,
        &candidate_hosts,
        Arc::clone(&cf_domains),
        tls_connector,
        &logger,
        peer,
    ).await {
        Some(b) => b,
        None => {
            logger
                .warn(&format!("[{}] Failed to connect to any backend for DC{}", peer, actual_dc))
                .await;
            return;
        }
    };

    let (mut client_reader, mut client_writer) = client_socket.into_split();
    let bytes_up = Arc::new(AtomicU64::new(0));
    let bytes_down = Arc::new(AtomicU64::new(0));

    match backend.stream {
        BackendStream::Tcp(mut tcp_stream) => {
            if let Err(e) = tcp_stream.write_all(&relay_init).await {
                logger.warn(&format!("[{}] Failed to send relay init via TCP: {}", peer, e)).await;
                return;
            }

            let (mut tcp_reader, mut tcp_writer) = tcp_stream.into_split();
            let bytes_up_clone = Arc::clone(&bytes_up);
            let client_to_tcp = async {
                let mut buf = vec![0u8; 65536];
                loop {
                    let n = match client_reader.read(&mut buf).await {
                        Ok(0) => break,
                        Ok(n) => n,
                        Err(_) => break,
                    };
                    bytes_up_clone.fetch_add(n as u64, Ordering::Relaxed);
                    let chunk = &buf[..n];
                    let mut plain = chunk.to_vec();
                    clt_dec.apply_keystream(&mut plain);
                    let mut cipher_chunk = plain;
                    tg_enc.apply_keystream(&mut cipher_chunk);
                    if let Err(_) = tcp_writer.write_all(&cipher_chunk).await {
                        break;
                    }
                }
            };

            let bytes_down_clone = Arc::clone(&bytes_down);
            let tcp_to_client = async {
                let mut buf = vec![0u8; 65536];
                loop {
                    let n = match tcp_reader.read(&mut buf).await {
                        Ok(0) => break,
                        Ok(n) => n,
                        Err(_) => break,
                    };
                    bytes_down_clone.fetch_add(n as u64, Ordering::Relaxed);
                    let chunk = &buf[..n];
                    let mut plain = chunk.to_vec();
                    tg_dec.apply_keystream(&mut plain);
                    let mut cipher_chunk = plain;
                    clt_enc.apply_keystream(&mut cipher_chunk);
                    if let Err(_) = client_writer.write_all(&cipher_chunk).await {
                        break;
                    }
                }
            };

            tokio::select! {
                _ = client_to_tcp => {},
                _ = tcp_to_client => {},
            }
        }
        BackendStream::Ws(mut ws) => {
            if let Err(e) = ws.send(Message::Binary(relay_init.into())).await {
                logger.warn(&format!("[{}] Failed to send relay init via WS: {}", peer, e)).await;
                return;
            }

            let (mut ws_sink, mut ws_src) = ws.split();
            let mut splitter = MsgSplitter::new(proto_tag);

            let bytes_up_clone = Arc::clone(&bytes_up);
            let client_to_ws = async {
                let mut buf = vec![0u8; 65536];
                loop {
                    let n = match client_reader.read(&mut buf).await {
                        Ok(0) => break,
                        Ok(n) => n,
                        Err(_) => break,
                    };

                    bytes_up_clone.fetch_add(n as u64, Ordering::Relaxed);
                    let chunk = &buf[..n];
                    let mut plain = chunk.to_vec();
                    clt_dec.apply_keystream(&mut plain);

                    let mut cipher_chunk = plain.clone();
                    tg_enc.apply_keystream(&mut cipher_chunk);

                    let parts = splitter.split(&cipher_chunk, &plain);
                    for part in parts {
                        if let Err(_) = ws_sink.send(Message::Binary(part.into())).await {
                            return;
                        }
                    }
                }
            };

            let bytes_down_clone = Arc::clone(&bytes_down);
            let ws_to_client = async {
                while let Some(msg_res) = ws_src.next().await {
                    let msg = match msg_res {
                        Ok(m) => m,
                        Err(_) => break,
                    };

                    match msg {
                        Message::Binary(data) => {
                            bytes_down_clone.fetch_add(data.len() as u64, Ordering::Relaxed);
                            let mut data_vec = data.to_vec();
                            tg_dec.apply_keystream(&mut data_vec);
                            clt_enc.apply_keystream(&mut data_vec);

                            if let Err(_) = client_writer.write_all(&data_vec).await {
                                break;
                            }
                        }
                        Message::Close(_) => break,
                        _ => {}
                    }
                }
            };

            tokio::select! {
                _ = client_to_ws => {},
                _ = ws_to_client => {},
            }
        }
    }

    logger
        .log(&format!(
            "[{}] Closed DC{} stream ({} bytes up, {} bytes down)",
            peer,
            actual_dc,
            bytes_up.load(Ordering::Relaxed),
            bytes_down.load(Ordering::Relaxed)
        ))
        .await;
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
    let tls_connector = Arc::new(create_fronting_tls_connector());
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
                let tls_clone = Arc::clone(&tls_connector);
                let logger_clone = logger.clone();
                tokio::spawn(async move {
                    handle_client(socket, peer, port, secret_clone, cf_clone, tls_clone, logger_clone).await;
                });
            }
            Err(e) => {
                logger.warn(&format!("Accept error: {}", e)).await;
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        }
    }
}
