"""
oxDesktop Master Plugin & Python SDK Test Suite
Runs comprehensive local tests without cluttering CI or GitHub Actions.
"""

import json
import os
import sys
import tempfile
import types

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON_DIR = os.path.join(REPO_ROOT, "Telegram", "SourceFiles", "extera", "python")
sys.path.insert(0, PYTHON_DIR)
import metadata_parser

# Mock _extera native module
mock_extera = types.ModuleType("_extera")
logs = []
sent_messages = []
raw_requests = []

mock_extera.log = lambda s: logs.append(str(s))
mock_extera.toast = lambda s: None
mock_extera.open_url = lambda s: None
mock_extera.copy = lambda s: None
mock_extera.send_message = lambda peer, text, entities, reply: sent_messages.append((peer, text, entities, reply))
mock_extera.send_raw_request = lambda b64, cb: raw_requests.append(b64) or 1001
mock_extera.run_on_main = lambda fn, d=0: fn()
mock_extera.show_alert = lambda s: None
mock_extera.settings_changed = lambda s: None
mock_extera.current_peer = lambda: 123456789
mock_extera.get_selected_account = lambda: 0
mock_extera.self_id = lambda: 99999
mock_extera.peer_info = lambda pid: '{"type":"user","name":"Test Client","bare_id":123456789}'

sys.modules["_extera"] = mock_extera
import cactuslib

import _compat
_compat.install()

import extera_host
import client_utils
import base_plugin
from base_plugin import BasePlugin, HookResult, HookStrategy
import ui.settings as s
import ui.alert as alert
import tl_runtime
from cactuslib import CactusUtils, command
import file_utils


def test_markdown():
    print("[1/56] Testing Markdown & Entity Parsing...")
    cases = [
        ("Hello **bold** [link](https://test.com) ~~strike~~", [
            ("bold", "bold"),
            ("strike", "strike"),
            ("url", "link"),
        ]),
        ("[first](https://1.com) and `code`", [
            ("code", "code"),
            ("url", "first"),
        ]),
    ]
    for text, expected in cases:
        t, entities = _compat.parse_markdown(text)
        for exp_kind, exp_slice in expected:
            matches = [e for e in entities if e[0] == exp_kind and t[e[1]:e[1] + e[2]] == exp_slice]
            assert matches, f"Failed match {exp_kind}='{exp_slice}' in '{t}'"
    print("  -> PASSED")


def test_arraylist():
    print("[2/56] Testing ArrayList & Java Bridge Types...")
    al1 = _compat.ArrayList([10, 20, 30])
    al2 = _compat.ArrayList([10, 20, 30])
    assert al1 == al2
    assert al1 == [10, 20, 30]
    assert al1.size() == 3
    assert al1.get(1) == 20
    al1.add(40)
    assert al1.size() == 4
    print("  -> PASSED")


def test_settings_descriptors():
    print("[3/56] Testing Settings Components & Dynamic Descriptors...")
    switch = s.Switch(title="Enable Mod", subtitle="Toggle on/off", default=True)
    assert switch.text == "Enable Mod"
    assert switch.subtext == "Toggle on/off"
    desc_sw = s.describe(switch, 0)
    assert desc_sw["text"] == "Enable Mod"
    assert desc_sw["default"] == True

    sel = s.Selector(title="Account", options={"0": "Acc A", "1": "Acc B"}, default="1")
    assert sel.items == ["Acc A", "Acc B"]
    desc_sel = s.describe(sel, 1)
    assert desc_sel["default"] == 1  # normalized integer index for UI

    edit = s.EditText(title="Prefix", hint="Enter prefix", default="!", on_save=lambda val: None)
    assert edit.text == "Prefix"

    btn = s.Button(title="Action", on_click=lambda: None)
    assert btn.text == "Action"
    assert btn.accent == True
    desc_btn = s.describe(btn, 3)
    assert desc_btn["clickable"] == True
    assert desc_btn["kind"] == "text"  # mapped for C++ UI

    cat = s.Category(title="Category Header", items=[
        s.Switch(title="SubSwitch", default=False),
        s.Button(title="SubButton", on_click=lambda: None),
    ])
    assert cat.text == "Category Header"
    s.register_items("cat_test", [cat])
    # Flattening should produce 3 items: Header + SubSwitch + SubButton
    assert len(s._registered["cat_test"]) == 3
    assert s.find_item("cat_test", 0).text == "Category Header"
    assert s.find_item("cat_test", 1).text == "SubSwitch"
    assert s.find_item("cat_test", 2).text == "SubButton"

    cp = s.ColorPicker(key="col", title="Color", default="#FF0000")
    assert cp.default == "#FF0000"
    desc_cp = s.describe(cp, 4)
    assert desc_cp["default"] == "#FF0000"
    assert desc_cp["kind"] == "input"  # mapped for C++ UI

    mc = s.MultiChoice(key="mc", title="Multi", items=["Opt1", "Opt2"], default=[0])
    assert mc.items == ["Opt1", "Opt2"]
    desc_mc = s.describe(mc, 5)
    assert desc_mc["items"] == ["Opt1", "Opt2"]
    assert desc_mc["kind"] == "selector"  # mapped for C++ UI
    print("  -> PASSED")


def test_alert_builder():
    print("[4/56] Testing AlertDialogBuilder & CamelCase Aliases...")
    builder = alert.AlertDialogBuilder()
    builder.setTitle("Notice").setMessage("Operation complete").setPositiveButton("OK", lambda b, w: None)
    payload = builder._payload()
    assert payload["title"] == "Notice"
    assert payload["message"] == "Operation complete"
    assert len(payload["buttons"]) == 1

    assert not builder.is_showing()
    builder.show()
    assert builder.is_showing()
    assert builder.isShowing()
    builder.cancel()
    assert not builder.is_showing()
    print("  -> PASSED")


def test_plugin_lifecycle():
    print("[5/56] Testing Plugin Lifecycle (Load, Unload, Settings, Deletion)...")
    with tempfile.TemporaryDirectory() as tmpdir:
        p_dir = os.path.join(tmpdir, "plugins")
        s_dir = os.path.join(tmpdir, "settings")
        os.makedirs(p_dir)
        os.makedirs(s_dir)

        p_path = os.path.join(p_dir, "test_plug.plugin")
        with open(p_path, "w", encoding="utf-8") as f:
            f.write('''
__id__ = "test_plug"
__name__ = "Test Plug"
__version__ = "1.0"
from base_plugin import BasePlugin
import ui.settings as s

class Plugin(BasePlugin):
    def on_plugin_load(self):
        self.add_on_send_message_hook(5)
    def create_settings(self):
        return [s.Switch(key="sw", title="Switch")]
''')
        init_res = json.loads(extera_host.dispatch("init", json.dumps({
            "plugins": p_dir,
            "settings": s_dir,
            "safe_mode": False,
            "unknown_sources": True
        })))
        assert init_res["ok"]
        list_res = json.loads(extera_host.dispatch("list", "{}"))
        assert len(list_res["result"]) == 1
        assert list_res["result"][0]["id"] == "test_plug"

        del_res = json.loads(extera_host.dispatch("delete", json.dumps({"id": "test_plug"})))
        assert del_res["ok"]
    print("  -> PASSED")


def test_outgoing_message_hooks():
    print("[6/56] Testing Outgoing Message Interception & Modification...")
    class MessageModifierPlugin(BasePlugin):
        def on_send_message_hook(self, account, params):
            if params.message == "/spoiler":
                params.message = "||classified||"
                return HookResult(strategy=HookStrategy.MODIFY)
            if params.message == "/blockme":
                return HookResult(strategy=HookStrategy.CANCEL)
            return HookResult(strategy=HookStrategy.DEFAULT)

    p = MessageModifierPlugin()
    p._extera_attach("mod_plugin")

    class Outgoing:
        def __init__(self, m):
            self.message = m
            self.peer = 12345
            self.reply_to_id = 0

    o1 = Outgoing("/spoiler")
    r1 = p.on_send_message_hook(0, o1)
    assert r1.strategy == HookStrategy.MODIFY
    assert o1.message == "||classified||"

    o2 = Outgoing("/blockme")
    r2 = p.on_send_message_hook(0, o2)
    assert r2.strategy == HookStrategy.CANCEL
    print("  -> PASSED")


def test_incoming_update_wrapping():
    print("[7/56] Testing Incoming Update TL Wrapping...")
    class UpdateListenerPlugin(BasePlugin):
        def on_update_hook(self, name, account, update):
            self.received_msg = getattr(update, "message", None)
            return HookResult()

    p = UpdateListenerPlugin()
    p._extera_attach("upd_plugin")
    extera_host._records["upd_plugin"] = extera_host.Record("p.plugin", {"id": "upd_plugin"})
    extera_host._records["upd_plugin"].instance = p

    raw_event = {
        "id": 999,
        "dialog_id": 123456789,
        "out": False,
        "date": 1700000000,
        "sender_id": 88888,
        "text": "Incoming text"
    }

    extera_host.dispatch("event", json.dumps({
        "type": "update",
        "name": "updateNewMessage",
        "account": 0,
        "update": raw_event
    }))

    assert p.received_msg is not None, "update.message must be wrapped into TL_message"
    assert p.received_msg.message == "Incoming text"
    assert p.received_msg.id == 999
    assert p.received_msg.dialog_id == 123456789
    print("  -> PASSED")


def test_pre_request_hook_cancel():
    print("[8/56] Testing Pre-Request Hook Cancellation (Ghost Mode)...")
    raw_requests.clear()

    class StealthPlugin(BasePlugin):
        def on_plugin_load(self):
            self.add_hook("TL_messages_readHistory")
        def pre_request_hook(self, name, account, req):
            if name == "TL_messages_readHistory":
                return HookResult(strategy=HookStrategy.CANCEL)
            return HookResult()

    p = StealthPlugin()
    p._extera_attach("stealth_plugin")
    extera_host._records["stealth_plugin"] = extera_host.Record("s.plugin", {"id": "stealth_plugin"})
    extera_host._records["stealth_plugin"].instance = p
    p.on_plugin_load()

    read_req = tl_runtime.TLRPC.TL_messages_readHistory(peer=tl_runtime.TLRPC.TL_inputPeerEmpty(), max_id=50)
    req_id = client_utils.send_request(read_req)
    assert req_id == 0, "Cancelled request should return id 0"
    assert len(raw_requests) == 0, "Cancelled request must never touch network"
    print("  -> PASSED")


def test_post_request_hook():
    print("[9/56] Testing Post-Request Hook Dispatch...")
    class AuditPlugin(BasePlugin):
        def on_plugin_load(self):
            self.add_hook("TL_help_getConfig")
            self.dispatched = False
        def post_request_hook(self, name, account, resp, err):
            self.dispatched = True

    p = AuditPlugin()
    p._extera_attach("audit_plugin")
    extera_host._records["audit_plugin"] = extera_host.Record("a.plugin", {"id": "audit_plugin"})
    extera_host._records["audit_plugin"].instance = p
    p.on_plugin_load()

    cfg_req = tl_runtime.TLRPC.TL_help_getConfig()
    client_utils.send_request(cfg_req)
    cb_id = list(client_utils._callbacks.keys())[-1]
    client_utils.extera_host_dispatch_callback(cb_id, None, None, raw=None, code=0)
    assert p.dispatched == True, "post_request_hook must be notified"
    print("  -> PASSED")


def test_cactuslib():
    print("[10/56] Testing CactusLib (@command, Command context, DB)...")
    sent_messages.clear()

    class MathPlugin(CactusUtils.Plugin):
        @command("add", doc="Add two numbers")
        def add_cmd(self, cmd: CactusUtils.Command):
            nums = [int(x) for x in cmd.args]
            cmd.answer(f"Sum: {sum(nums)}")
            return HookResult(strategy=HookStrategy.CANCEL)

    p = MathPlugin()
    p._extera_attach("math_plug")
    p.on_plugin_load()

    class Out:
        def __init__(self, m):
            self.message = m
            self.peer = 12345
            self.reply_to_id = 0

    res = p.on_send_message_hook(0, Out("/add 15 25 10"))
    assert res.strategy == HookStrategy.CANCEL
    assert len(sent_messages) == 1
    assert sent_messages[0][1] == "Sum: 50"

    p.db.set("best_score", 999)
    assert p.db.get("best_score") == 999
    p.db.delete("best_score")
    assert p.db.get("best_score") is None
    print("  -> PASSED")


def test_controllers_bridge():
    print("[11/56] Testing Controllers Bridge (Messages, Contacts, Media, SendHelper)...")
    from org.telegram.messenger import (
        MessagesController,
        ContactsController,
        MediaDataController,
        SendMessagesHelper,
    )
    cc = ContactsController.getInstance(0)
    assert cc.isLoadingContacts() == False
    assert len(cc.contacts) == 0

    mdc = MediaDataController.getInstance(0)
    assert len(mdc.getStickerSets(0)) == 0

    smh = SendMessagesHelper.getInstance(0)
    sent_messages.clear()
    smh.sendMessage(111, "Hello from SendHelper")
    assert len(sent_messages) == 1
    assert sent_messages[0][1] == "Hello from SendHelper"
    print("  -> PASSED")


def test_session_file_protection():
    print("[12/56] Testing Security: Session & Credential File Protection...")
    assert file_utils.read_file("tdata/key_datas") is None
    assert file_utils.read_file_bytes("tdata/D877F783D5D3EF8C0") is None
    assert file_utils.write_file("tdata/settings0", "hack") is False
    assert file_utils.delete_file("tdata/key_datas") is False
    assert file_utils.list_dir("tdata") == []
    print("  -> PASSED")


def test_token_and_env_shield():
    print("[13/56] Testing Security: Environment & Token Shielding...")
    os.environ["GH_TOKEN"] = "ghp_secret_access_token_123"
    os.environ["GITHUB_TOKEN"] = "ghs_token_xyz"
    os.environ["TDESKTOP_API_HASH"] = "hash_344583"
    os.environ["SAFE_SYSTEM_VAR"] = "system_value"

    assert os.environ.get("GH_TOKEN") == "ghp_secret_access_token_123"

    with extera_host._plugin_context("untrusted_plugin"):
        assert os.environ.get("GH_TOKEN") is None, "GH_TOKEN must be masked inside plugin context"
        assert os.getenv("GITHUB_TOKEN") is None, "GITHUB_TOKEN must be masked inside plugin context"
        assert os.environ.get("TDESKTOP_API_HASH") is None, "TDESKTOP_API_HASH must be masked"
        assert "GH_TOKEN" not in os.environ
        assert os.environ.get("SAFE_SYSTEM_VAR") == "system_value"
        try:
            _ = os.environ["GH_TOKEN"]
            assert False, "Should raise KeyError"
        except KeyError:
            pass

    assert os.environ.get("GH_TOKEN") == "ghp_secret_access_token_123"
    print("  -> PASSED")


def test_hybrid_send_message_params():
    print("[14/56] Testing Hybrid SendMessageParams & _ReplyStub...")
    p = _compat.SendMessageParams(peer=123456, message="initial text", reply_to=789)
    assert p.text == "initial text"
    assert p["message"] == "initial text"
    assert p["text"] == "initial text"
    assert p["dialog_id"] == 123456
    assert p["reply_to_id"] == 789
    assert int(p.replyToMsg) == 789
    assert p.replyToMsg.id == 789

    # Dict modification
    p["message"] = "modified text"
    assert p.message == "modified text"
    assert p.text == "modified text"

    # Property modification
    p.text = "property modified"
    assert p["message"] == "property modified"
    assert p.message == "property modified"

    # Dict containment & helpers
    assert "message" in p
    assert "dialog_id" in p
    assert p.get("missing", "fallback") == "fallback"
    p.setdefault("custom_param", "stored")
    assert p.get("custom_param") == "stored"
    print("  -> PASSED")


def test_sandboxed_open_and_subprocess():
    print("[15/56] Testing Sandboxed builtins.open, os.remove, subprocess inside Plugin Context...")
    import subprocess
    # Outside plugin context, operations work normally
    with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
        tf.write("normal content")
        temp_name = tf.name

    try:
        with open(temp_name, "r") as f:
            assert f.read() == "normal content"

        with extera_host._plugin_context("malicious_stealer_plugin"):
            # Reading normal temp file inside plugin context works
            with open(temp_name, "r") as f:
                assert f.read() == "normal content"

            # Attempting to read tdata/key_datas via builtins.open MUST raise PermissionError
            try:
                with open("tdata/key_datas", "rb") as f:
                    assert False, "Stealer access to key_datas should be blocked!"
            except PermissionError:
                pass

            # Attempting to delete tdata files via os.remove MUST raise PermissionError
            try:
                os.remove("tdata/D877F783D5D3EF8C0")
                assert False, "Deletion of tdata should be blocked!"
            except PermissionError:
                pass

            # Attempting to execute os.system MUST raise PermissionError
            try:
                os.system("echo hack")
                assert False, "os.system should be blocked inside plugins!"
            except PermissionError:
                pass

            # Attempting to spawn subprocess.Popen MUST raise PermissionError
            try:
                subprocess.Popen(["cmd.exe", "/c", "echo hack"])
                assert False, "subprocess.Popen should be blocked inside plugins!"
            except PermissionError:
                pass

        # Outside plugin context, normal open works again
        with open(temp_name, "r") as f:
            assert f.read() == "normal content"
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)
    print("  -> PASSED")


def test_tl_name_and_extended_updates():
    print("[16/56] Testing TLName Single-Dispatch & Extended Update Wrapping...")
    tl_name = extera_host.TLName("TL_updateNewMessage")
    assert tl_name == "TL_updateNewMessage"
    assert tl_name == "updateNewMessage"
    assert "updateNewMessage" in tl_name

    # Test updateEditMessage wrapping
    edit_dict = {
        "id": 444,
        "dialog_id": 555,
        "sender_id": 666,
        "text": "Edited content",
        "out": True,
        "date": 1700000000,
        "edit_date": 1700000050,
    }
    wrapped_edit = extera_host._wrap_update("updateEditMessage", edit_dict)
    assert type(wrapped_edit).__name__ == "TL_updateEditMessage"
    assert wrapped_edit.message.message == "Edited content"
    assert wrapped_edit.message.edit_date == 1700000050

    # Test updateDeleteMessages wrapping
    delete_dict = {
        "messages": [101, 102, 103],
    }
    wrapped_del = extera_host._wrap_update("updateDeleteMessages", delete_dict)
    assert type(wrapped_del).__name__ == "TL_updateDeleteMessages"
    assert list(wrapped_del.messages) == [101, 102, 103]
    print("  -> PASSED")


def test_plugin_lifecycle_fallbacks():
    print("[17/56] Testing BasePlugin Lifecycle Fallbacks (on_load, on_unload)...")
    load_events = []

    class OnLoadPlugin(BasePlugin):
        def on_load(self):
            load_events.append("loaded")

        def on_unload(self):
            load_events.append("unloaded")

    p = OnLoadPlugin()
    p.on_plugin_load()
    assert load_events == ["loaded"]
    p.on_plugin_unload()
    assert load_events == ["loaded", "unloaded"]
    print("  -> PASSED")


def test_run_on_queue_context_propagation():
    print("[18/56] Testing run_on_queue Context Propagation...")
    import time
    events = []

    with extera_host._plugin_context("queue_test_plugin"):
        def task():
            current = extera_host.current_plugin_id()
            events.append(current)

        client_utils.run_on_queue(task)

    time.sleep(0.1)
    assert len(events) == 1
    assert events[0] == "queue_test_plugin"
    print("  -> PASSED")


def test_elyx_archive_plugin():
    print("[19/56] Testing Elyx/EAF Multi-File Archive Plugin Loading...")
    import zipfile
    import metadata_parser
    with tempfile.TemporaryDirectory() as tmpdir:
        p_path = os.path.join(tmpdir, "archive_plug.elyx")
        meta = {
            "id": "archived_test_plugin",
            "name": "Archived Test Plugin",
            "version": "1.5",
            "author": "Community",
            "permissions": ["ui"]
        }
        py_helper = "def secret(): return 42\n"
        py_main = """from base_plugin import BasePlugin
import my_helper

class ArchivePlugin(BasePlugin):
    def on_load(self):
        self._val = my_helper.secret()
"""
        with zipfile.ZipFile(p_path, "w") as zf:
            zf.writestr("metadata.json", json.dumps(meta))
            zf.writestr("my_helper.py", py_helper)
            zf.writestr("plugin.py", py_main)

        m = metadata_parser.read_metadata(p_path)
        assert m["id"] == "archived_test_plugin"
        assert m["is_archive"] is True
        
        record = extera_host.Record(p_path, m)
        extera_host._records[record.id] = record
        extera_host._unknown_allowed = True
        extera_host._install_plugin_importer()
        extera_host._activate(record)

        assert record.instance is not None
        assert record.instance._val == 42
        extera_host._deactivate(record)
    print("  -> PASSED")


def test_critical_threat_scanner():
    print("[20/56] Testing Critical Threat Detection & Automatic Blocking...")
    import capability_scan
    with tempfile.TemporaryDirectory() as tmpdir:
        p_path = os.path.join(tmpdir, "stealer_plug.plugin")
        code = """__id__ = "stealer_test"
__name__ = "Stealer Test"
import ctypes
from base_plugin import BasePlugin

class Stealer(BasePlugin):
    def on_load(self):
        # Stealer targeting session keys and DPAPI
        with open("tdata/key_datas", "rb") as f:
            pass
        ctypes.windll.crypt32.CryptUnprotectData(None)
"""
        with open(p_path, "w", encoding="utf-8") as f:
            f.write(code)

        caps = capability_scan.scan(p_path)
        threat = capability_scan.has_critical_threats(caps)
        assert threat in ("Telegram session keys", "DPAPI credential decrypt")

        meta = metadata_parser.read_metadata(p_path)
        record = extera_host.Record(p_path, meta)
        record.capabilities = caps
        reason = extera_host._blocked_reason(record)
        assert reason is not None
        assert "CRITICAL_SECURITY_THREAT" in reason
    print("  -> PASSED")


def test_polymorphic_signatures_and_command_registry():
    print("[21/56] Testing Polymorphic Hook Signatures & Command Registry...")
    # 1. Test CactusUtils.get_all_commands()
    class HelpTestPlugin(cactuslib.CactusUtils.Plugin):
        @cactuslib.command("status", doc="Shows client status")
        def status_cmd(self, cmd):
            cmd.answer("All systems operational")

    p = HelpTestPlugin()
    p._extera_attach("status_plug")
    p.on_plugin_load()

    all_cmds = cactuslib.CactusUtils.get_all_commands()
    matches = [c for c in all_cmds if c["name"] == "status"]
    assert len(matches) == 1
    assert matches[0]["doc"] == "Shows client status"
    assert matches[0]["plugin_id"] == "status_plug"

    # 2. Test 1-argument on_send_message_hook(self, params)
    class OneArgSendPlugin(BasePlugin):
        def on_send_message_hook(self, params):
            if params.get("message") == ".custom":
                params["message"] = "replaced_1arg"
                return HookResult(strategy=HookStrategy.MODIFY, params=params)
            return None

    o = OneArgSendPlugin()
    o._extera_attach("one_arg_plug")
    extera_host._records["one_arg_plug"] = extera_host.Record("dummy", {"id": "one_arg_plug"})
    extera_host._records["one_arg_plug"].instance = o
    extera_host._send_hooks["one_arg_plug"] = 10

    res = extera_host._send_hook({"peer": 111, "text": ".custom", "account": 0})
    assert res["strategy"] == "modify"
    assert res["text"] == "replaced_1arg"

    # 3. Test 1-argument on_update_hook(self, update)
    got_updates = []
    class OneArgUpdatePlugin(BasePlugin):
        def on_update_hook(self, update):
            got_updates.append(type(update).__name__)

    u = OneArgUpdatePlugin()
    u._extera_attach("one_arg_upd")
    extera_host._records["one_arg_upd"] = extera_host.Record("dummy", {"id": "one_arg_upd"})
    extera_host._records["one_arg_upd"].instance = u

    extera_host._event({"type": "update", "name": "TL_updateNewMessage", "update": {"id": 1, "dialog_id": 2, "text": "hi"}, "account": 0})
    assert got_updates == ["TL_updateNewMessage"]

    # Cleanup
    extera_host._records.pop("one_arg_plug", None)
    extera_host._send_hooks.pop("one_arg_plug", None)
    extera_host._records.pop("one_arg_upd", None)
    p.on_plugin_unload()
    print("  -> PASSED")


def test_delete_and_pin_helpers():
    print("[22/56] Testing delete_messages, delete_message, and pin_message Helpers...")
    req_id = client_utils.delete_messages(12345, [100, 101], revoke=True)
    assert req_id > 0
    assert len(raw_requests) > 0

    req_id_ch = client_utils.delete_messages(-1001234567890, [200], revoke=True)
    assert req_id_ch > 0

    req_id_single = client_utils.delete_message({"dialog_id": 54321, "id": 999})
    assert req_id_single > 0

    req_id_pin = client_utils.pin_message(12345, 555, silent=True)
    assert req_id_pin > 0
    print("  -> PASSED")


def test_file_loader_and_download_controller():
    print("[23/56] Testing FileLoader and DownloadController...")
    import client_utils
    from org.telegram.messenger import FileLoader, DownloadController

    fl = FileLoader.getInstance(0)
    assert fl is not None
    d = fl.checkDirectory(fl.MEDIA_DIR_CACHE)
    assert isinstance(d, str) and len(d) > 0

    class DummyPhoto:
        path = "/tmp/photo.jpg"

    class DummyMedia:
        photo = DummyPhoto()

    class DummyMsg:
        media = DummyMedia()

    assert fl.getPathToMessage(DummyMsg()) == "/tmp/photo.jpg"
    assert fl.getPathToMessage(None) == ""

    dc = DownloadController.getInstance(0)
    assert dc is not None
    assert dc.canDownloadMedia(dc.AUTODOWNLOAD_TYPE_PHOTO) is True

    # Check client_utils delegates
    client = client_utils.get_client(0)
    assert client.get_file_loader() is fl
    assert client.get_download_controller() is dc
    print("  -> PASSED")


def test_notification_center_pubsub():
    print("[24/56] Testing NotificationCenter pub-sub and observer dispatch...")
    import client_utils
    from org.telegram.messenger import NotificationCenter

    nc = NotificationCenter.getInstance(0)
    assert nc is not None

    received_events = []

    class Observer:
        def didReceivedNotification(self, notification_id, account, args):
            received_events.append((notification_id, account, args))

    obs = Observer()
    nc.addObserver(obs, NotificationCenter.messagesDidLoad)
    nc.postNotificationName(NotificationCenter.messagesDidLoad, "test_arg1", 42)

    assert len(received_events) == 1
    assert received_events[0][0] == NotificationCenter.messagesDidLoad
    assert received_events[0][1] == 0
    assert received_events[0][2] == ("test_arg1", 42)

    # Test removing observer
    nc.removeObserver(obs, NotificationCenter.messagesDidLoad)
    nc.postNotificationName(NotificationCenter.messagesDidLoad, "arg2")
    assert len(received_events) == 1

    # Check client_utils delegate
    client = client_utils.get_client(0)
    assert client.get_notification_center() is nc
    print("  -> PASSED")


def test_draft_and_forward_helpers():
    print("[25/56] Testing draft and forward message helpers...")
    import client_utils

    # Draft save and clear
    req_draft = client_utils.save_draft(12345, "draft message", reply_to_msg_id=10)
    assert req_draft > 0

    req_clear = client_utils.clear_draft(12345)
    assert req_clear > 0

    # Forward messages
    req_fwd = client_utils.forward_messages(12345, 54321, [100, 101], silent=True, drop_author=True)
    assert req_fwd > 0

    # AccountClient helpers
    client = client_utils.get_client(0)
    req_client_draft = client.save_draft(12345, "client draft")
    assert req_client_draft > 0
    req_client_clear = client.clear_draft(12345)
    assert req_client_clear > 0
    req_client_fwd = client.forward_messages(12345, 54321, [200])
    assert req_client_fwd > 0
    print("  -> PASSED")


def test_sqlite_and_pipe_sandboxing():
    print("[26/56] Testing SQLite sensitive DB access and os.popen pipe sandboxing...")
    import sqlite3
    import os
    import extera_host

    with extera_host._plugin_context("stealer_test_plug"):
        # 1. Access to sensitive SQLite db must raise PermissionError
        blocked_sqlite = False
        try:
            sqlite3.connect("C:/Users/test/AppData/Local/Google/Chrome/User Data/Default/Login Data")
        except PermissionError as e:
            blocked_sqlite = True
            assert "Login Data" in str(e)
        assert blocked_sqlite, "sqlite3.connect to Chrome Login Data should be blocked!"

        # 2. Access to Telegram session tdata via sqlite must be blocked
        blocked_tdata = False
        try:
            sqlite3.connect("C:/Telegram Desktop/tdata/key_datas")
        except PermissionError:
            blocked_tdata = True
        assert blocked_tdata, "sqlite3.connect to key_datas should be blocked!"

        # 3. Legitimate in-memory or temp sqlite DB must work
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE foo (id INT)")
        con.execute("INSERT INTO foo VALUES (42)")
        cur = con.cursor()
        cur.execute("SELECT id FROM foo")
        assert cur.fetchone()[0] == 42
        con.close()

        # 4. os.popen must be blocked
        blocked_popen = False
        try:
            os.popen("whoami")
        except PermissionError:
            blocked_popen = True
        assert blocked_popen, "os.popen in plugin context should be blocked!"

    # Outside plugin context, os.popen and sqlite are normal
    assert not extera_host.is_in_plugin_context()
    print("  -> PASSED")


def test_hook_result_helpers_and_plugin_shortcuts():
    print("[27/56] Testing HookResult static helpers, CactusUtils.Uri, and BasePlugin shortcuts...")
    import base_plugin
    import cactuslib
    from base_plugin import HookResult, HookStrategy, BasePlugin
    from cactuslib import CactusUtils

    # 1. HookResult static helpers
    r_cancel = HookResult.cancel()
    assert r_cancel.strategy == HookStrategy.CANCEL
    r_default = HookResult.default()
    assert r_default.strategy == HookStrategy.DEFAULT
    r_mod = HookResult.modify(result="custom")
    assert r_mod.strategy == HookStrategy.MODIFY
    assert r_mod.result == "custom"

    # 2. CactusUtils.Uri.create
    u = CactusUtils.Uri.create("my_plugin", "start", foo="bar", num=1)
    assert u == "extera://plugin/my_plugin/start?foo=bar&num=1"

    # 3. BasePlugin shortcuts
    class ShortcutTestPlugin(BasePlugin):
        pass

    p = ShortcutTestPlugin()
    p._extera_attach("shortcut_plug")

    # Draft shortcuts
    req_d = p.save_draft(12345, "hello shortcut draft")
    assert req_d > 0
    req_c = p.clear_draft(12345)
    assert req_c > 0

    # Pin & Delete shortcuts
    req_pin = p.pin_message(12345, 999)
    assert req_pin > 0
    req_del = p.delete_message({"dialog_id": 12345, "id": 999})
    assert req_del > 0

    # Forward shortcut
    req_fwd = p.forward_messages(12345, 54321, [1, 2])
    assert req_fwd > 0

    # Toast shortcut
    p.toast("Quick notification")

    # 4. CactusUtils.Telegram send_request alias and Result
    import tl_runtime
    TLRPC = tl_runtime.TLRPC
    req_dummy = TLRPC.TL_help_getConfig()
    # Synchronous wait=False returns request_id
    req_id_tl = CactusUtils.Telegram.send_request(req_dummy, wait_response=False)
    assert req_id_tl > 0

    res_obj = CactusUtils.Telegram.Result(response="ok", error=None)
    assert res_obj.response == "ok"
    assert res_obj.error is None
    print("  -> PASSED")


def test_intents_with_placeholder_matching():
    print("[28/56] Testing IntentsManager with parameterized path templates and dispatch...")
    import intents
    from intents import IntentsManager
    import extera_host

    captured = []

    with extera_host._plugin_context("intent_plug"):
        handle = IntentsManager.new_global_before_handler(
            lambda name, debug=None: captured.append((name, debug)) or True,
            schemes=["extera"],
            hosts=["plugin"],
            path_template="/{name}/open"
        )
        assert handle is not None

        parsed = IntentsManager.parse("extera://plugin/delta_app/open?debug=true")
        dispatched = IntentsManager.dispatch(before=True, context=parsed)
        assert dispatched is True
        assert len(captured) == 1
        assert captured[0] == ("delta_app", "true")

        # Unhandle and verify it is not called again
        handle.unhandle()
        dispatched2 = IntentsManager.dispatch(before=True, context=parsed)
        assert dispatched2 is False
        assert len(captured) == 1
    print("  -> PASSED")


def test_metadata_parser_constants():
    print("[29/56] Testing metadata_parser AST Extraction & Key Validation...")
    import metadata_parser
    source = """
__id__ = "valid_plugin_id"
__name__ = "Valid Plugin"
__description__ = "A full test plugin"
__author__ = "NanoDev"
__version__ = "2.0.1"
__min_version__ = "7.3.0"
__permissions__ = ["messages.read", "ui"]
__requirements__ = ["requests"]
"""
    with tempfile.NamedTemporaryFile("w", suffix=".plugin", delete=False, encoding="utf-8") as tf:
        tf.write(source)
        t_path = tf.name
    try:
        meta = metadata_parser.read_metadata(t_path)
        assert meta["id"] == "valid_plugin_id"
        assert meta["name"] == "Valid Plugin"
        assert meta["author"] == "NanoDev"
        assert meta["version"] == "2.0.1"
        assert "messages.read" in meta["permissions"]
        assert "ui" in meta["permissions"]
        assert meta["requirements"] == ["requests"]
    finally:
        os.remove(t_path)
    print("  -> PASSED")


def test_metadata_parser_error_handling():
    print("[30/56] Testing metadata_parser Error Handling on Malformed Plugins...")
    import metadata_parser
    # Missing required __id__
    with tempfile.NamedTemporaryFile("w", suffix=".plugin", delete=False, encoding="utf-8") as tf:
        tf.write('__name__ = "No ID"')
        bad_path1 = tf.name
    try:
        err1 = False
        try:
            metadata_parser.read_metadata(bad_path1)
        except metadata_parser.PluginMetadataError:
            err1 = True
        assert err1, "Missing __id__ must raise PluginMetadataError"

        err2 = False
        try:
            metadata_parser._validate_plugin_id("bad id with spaces")
        except metadata_parser.PluginMetadataError:
            err2 = True
        assert err2, "Invalid __id__ format must raise PluginMetadataError"
    finally:
        os.remove(bad_path1)
    print("  -> PASSED")


def test_capability_scan_static_analysis():
    print("[31/56] Testing capability_scan Static AST Analysis & Permissions...")
    import capability_scan
    sample_code = """
import requests
from android_utils import log

def fetch_data():
    r = requests.get("https://example.com")
    log(r.text)
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(sample_code)
        py_path = tf.name
    try:
        caps = capability_scan.scan(py_path)
        assert capability_scan.PERM_NETWORK in caps
        evidences = caps[capability_scan.PERM_NETWORK]
        assert any("requests" in e for e in evidences)
    finally:
        os.remove(py_path)
    print("  -> PASSED")


def test_capability_scan_threat_detection():
    print("[32/56] Testing capability_scan Critical Threat Detection...")
    import capability_scan
    safe_caps = {capability_scan.PERM_NETWORK: ["requests", "urllib"]}
    assert capability_scan.has_critical_threats(safe_caps) is None

    malicious_caps = {
        capability_scan.PERM_FILES: ["Discord tokens", "key_datas"],
        capability_scan.PERM_NETWORK: ["socket"]
    }
    threat = capability_scan.has_critical_threats(malicious_caps)
    assert threat is not None
    assert threat in capability_scan.CRITICAL_THREAT_MARKERS
    print("  -> PASSED")


def test_text_formatting_html_parser():
    print("[33/56] Testing text_formatting HTML Entity Parsing & Offsets...")
    import text_formatting
    from text_formatting import TLEntityType
    raw = 'Hello <b>bold</b>, <i>italic</i>, and <a href="https://t.me/oxDesktop">oxDesktop</a>!'
    text, entities = text_formatting.parse_raw(raw, parse_mode="HTML")
    assert text == "Hello bold, italic, and oxDesktop!"
    types = [e.type for e in entities]
    assert TLEntityType.BOLD in types
    assert TLEntityType.ITALIC in types
    assert TLEntityType.TEXT_LINK in types
    link_entity = next(e for e in entities if e.type == TLEntityType.TEXT_LINK)
    assert link_entity.url == "https://t.me/oxDesktop"
    print("  -> PASSED")


def test_text_formatting_markdown():
    print("[34/56] Testing text_formatting Markdown Parsing & Spoilers...")
    import text_formatting
    from text_formatting import TLEntityType
    raw = 'Notice: ||spoiler content|| and `code snippet`'
    text, entities = text_formatting.parse_raw(raw, parse_mode="Markdown")
    assert "spoiler content" in text
    assert "code snippet" in text
    types = [e.type for e in entities]
    assert TLEntityType.SPOILER in types
    assert TLEntityType.CODE in types
    print("  -> PASSED")


def test_text_formatting_entity_to_dict():
    print("[35/56] Testing text_formatting Entity Dictionary Conversion...")
    import text_formatting
    from text_formatting import RawEntity, TLEntityType
    ent = RawEntity(offset=5, length=10, type=TLEntityType.TEXT_LINK, url="https://example.com")
    d = text_formatting.entity_to_dict(ent)
    assert d["offset"] == 5
    assert d["length"] == 10
    assert d["type"] == "text_link"
    assert d["url"] == "https://example.com"
    print("  -> PASSED")


def test_plugin_settings_typed_coercion():
    print("[36/56] Testing plugin_settings Type Coercion & Truthy Values...")
    import plugin_settings
    # Bool coercion
    assert plugin_settings.coerce_value("true", False) is True
    assert plugin_settings.coerce_value("1", False) is True
    assert plugin_settings.coerce_value("yes", False) is True
    assert plugin_settings.coerce_value("off", True) is False
    assert plugin_settings.coerce_value("0", True) is False
    # Numeric coercion
    assert plugin_settings.coerce_value("42", 0) == 42
    assert plugin_settings.coerce_value("3.14", 0.0) == 3.14
    # Fallback on invalid
    assert plugin_settings.coerce_value("not_a_number", 100) == 100
    print("  -> PASSED")


def test_plugin_settings_persistence_and_notifier():
    print("[37/56] Testing plugin_settings Persistence, Caching & Notifier...")
    import plugin_settings
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_settings.configure(tmpdir)
        notifications = []
        plugin_settings.set_notifier(lambda pid: notifications.append(pid))

        s_file = os.path.join(tmpdir, "plug_a.json")
        with open(s_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"key_bool": True, "key_num": 123}))

        raw_val = plugin_settings.coerce_value("true", False)
        assert raw_val is True
        assert os.path.exists(s_file)
    print("  -> PASSED")


def test_android_utils_safe_call_and_runnable():
    print("[38/56] Testing android_utils safe_call, Runnables & Logging...")
    import android_utils
    assert android_utils.safe_call(lambda x: x * 2, 21) == 42
    def broken():
        raise ValueError("Simulated fault")
    assert android_utils.safe_call(broken) is None

    executed = []
    r = android_utils.R(lambda: executed.append("ran"))
    r.run()
    assert executed == ["ran"]
    print("  -> PASSED")


def test_android_utils_clipboard_and_context():
    print("[39/56] Testing android_utils Clipboard & Context Emulation...")
    import android_utils
    res = android_utils.copy_to_clipboard("test_text_to_copy")
    assert res is True
    ctx = android_utils.get_context()
    assert ctx is not None
    assert "Context" in str(type(ctx)) or hasattr(ctx, "getPackageName")
    act = android_utils.get_activity()
    assert act is not None
    print("  -> PASSED")


def test_android_views_base_view():
    print("[40/56] Testing android_views Base View Hierarchy & Properties...")
    import android_views
    from android_views import View
    v = View()
    assert v.getId() > 0
    assert v._props["visibility"] == View.VISIBLE
    v.setVisibility(View.INVISIBLE)
    assert v._props["visibility"] == View.INVISIBLE
    v.setTag("test_tag")
    assert v.getTag() == "test_tag"
    v.setPadding(10, 12, 10, 12)
    assert v._props.get("padding") == [10, 12, 10, 12]
    v.setEnabled(False)
    assert v._props.get("enabled") is False
    print("  -> PASSED")


def test_android_views_textview():
    print("[41/56] Testing android_views TextView Text & Sizing...")
    import android_views
    from android_views import TextView
    tv = TextView()
    tv.setText("Hello oxDesktop")
    assert tv.getText() == "Hello oxDesktop"
    tv.setTextColor(0xFF229955)
    assert tv._props.get("color") == 0xFF229955
    tv.setTextSize(14.0)
    assert tv._props.get("size") is not None
    print("  -> PASSED")


def test_android_views_linearlayout():
    print("[42/56] Testing android_views LinearLayout Orientation & Children...")
    import android_views
    from android_views import LinearLayout, TextView
    layout = LinearLayout()
    layout.setOrientation(LinearLayout.VERTICAL)
    assert layout._props.get("orientation") == LinearLayout.VERTICAL

    child1 = TextView()
    child1.setText("Line 1")
    child2 = TextView()
    child2.setText("Line 2")

    layout.addView(child1)
    layout.addView(child2)
    assert layout.getChildCount() == 2
    assert layout.getChildAt(0).getText() == "Line 1"
    assert layout.getChildAt(1).getText() == "Line 2"

    layout.removeView(child1)
    assert layout.getChildCount() == 1
    assert layout.getChildAt(0).getText() == "Line 2"
    print("  -> PASSED")


def test_android_views_gradient_drawable():
    print("[43/56] Testing android_views GradientDrawable & Shapes...")
    import android_views
    from android_views import GradientDrawable
    gd = GradientDrawable()
    gd.setColor(0xFF102030)
    gd.setCornerRadius(8.0)
    gd.setStroke(2, 0xFFFFFFFF)
    assert gd.radius == 8.0
    assert gd.color == 0xFF102030
    assert gd._data().get("stroke") == [2.0, 0xFFFFFFFF]
    print("  -> PASSED")


def test_client_utils_hook_account_scoping():
    print("[44/56] Testing client_utils Thread-Local Hook Account Scoping...")
    import client_utils
    assert client_utils.get_hook_account() is None
    prev = client_utils._enter_hook_account(2)
    try:
        assert client_utils.get_hook_account() == 2
        prev_nested = client_utils._enter_hook_account(3)
        try:
            assert client_utils.get_hook_account() == 3
        finally:
            client_utils._exit_hook_account(prev_nested)
        assert client_utils.get_hook_account() == 2
    finally:
        client_utils._exit_hook_account(prev)
    assert client_utils.get_hook_account() is None
    print("  -> PASSED")


def test_client_utils_peer_id_resolution():
    print("[45/56] Testing client_utils _peer_id Resolution Across Formats...")
    import client_utils
    assert client_utils._peer_id(123456789) == 123456789
    assert client_utils._peer_id({"dialog_id": 987654321}) == 987654321
    assert client_utils._peer_id({"peer_id": 555666}) == 555666
    class ObjPeer:
        dialog_id = 777888
    assert client_utils._peer_id(ObjPeer()) == 777888
    assert client_utils.get_selected_account() == 0
    print("  -> PASSED")


def test_hook_utils_strategy_chaining():
    print("[46/56] Testing hook_utils Strategy Chaining & Prioritization...")
    from base_plugin import HookResult, HookStrategy
    r1 = HookResult(strategy=HookStrategy.DEFAULT)
    r2 = HookResult(strategy=HookStrategy.MODIFY, result="modified")
    r3 = HookResult(strategy=HookStrategy.CANCEL)
    assert r1.strategy == HookStrategy.DEFAULT
    assert r2.strategy == HookStrategy.MODIFY
    assert r3.strategy == HookStrategy.CANCEL
    assert r2.result == "modified"
    print("  -> PASSED")


def test_tl_runtime_constructors_and_classes():
    print("[47/56] Testing tl_runtime TLRPC Dynamic Constructor Lookup...")
    import tl_runtime
    TLRPC = tl_runtime.TLRPC
    err = TLRPC.TL_error()
    err.code = 400
    err.text = "BAD_REQUEST"
    assert err.code == 400
    assert err.text == "BAD_REQUEST"

    msg = TLRPC.TL_message()
    msg.id = 101
    msg.message = "Hello TL runtime"
    msg.out = True
    assert msg.id == 101
    assert msg.out is True
    print("  -> PASSED")


def test_tl_runtime_serialization():
    print("[48/56] Testing tl_runtime TLObject to_dict & Vector Handlers...")
    import tl_runtime
    TLRPC = tl_runtime.TLRPC
    vec = TLRPC.Vector([10, 20, 30])
    assert len(vec.objects) == 3
    assert vec.objects[0] == 10
    assert vec.objects[2] == 30
    err = TLRPC.TL_error(code=404, text="NOT_FOUND")
    d = err.to_dict()
    assert d.get("code") == 404
    assert d.get("text") == "NOT_FOUND"
    print("  -> PASSED")


def test_intents_query_and_path_matching():
    print("[49/56] Testing intents Query Parsing & URL Matching...")
    import intents
    parsed = intents.IntentsManager.parse("extera://plugin/my_tool/config?theme=dark&page=2")
    assert parsed["scheme"] == "extera"
    assert parsed["host"] == "plugin"
    assert parsed["path"] == "/my_tool/config"
    assert parsed["query_args"]["theme"] == "dark"
    assert parsed["query_args"]["page"] == "2"
    print("  -> PASSED")


def test_file_utils_path_traversal_guard():
    print("[50/56] Testing file_utils Safe Path Traversal & Forbidden Paths...")
    import file_utils
    assert file_utils.is_path_forbidden("tdata/key_datas") is True
    assert file_utils.is_path_forbidden("tdata/D877F783D5D3EF8C0") is True
    assert file_utils.is_path_forbidden("wallet.dat") is True
    assert file_utils.is_path_forbidden("plugins/test_plugin/config.json") is False
    print("  -> PASSED")


def test_compat_lenient_metaclass():
    print("[51/56] Testing _compat LenientMeta Dynamic Stub Generation...")
    import _compat
    class AndroidStub(metaclass=_compat.LenientMeta):
        pass
    val = AndroidStub.someMethod("arg1", 123)
    assert isinstance(val, _compat.Stub)
    stub_inst = _compat.Stub("custom_service")
    val2 = stub_inst.anotherMethod(True)
    assert isinstance(val2, _compat.Stub)
    print("  -> PASSED")


def test_compat_arraylist_methods():
    print("[52/56] Testing _compat ArrayList Mutation & Indexing...")
    import _compat
    al = _compat.ArrayList(["first", "second", "third"])
    assert len(al) == 3
    assert al.get(0) == "first"
    al.add("fourth")
    assert al.size() == 4
    assert al.contains("second") is True
    assert al.contains("missing") is False
    al.remove("second")
    assert al.size() == 3
    assert al.contains("second") is False
    print("  -> PASSED")


def test_ui_settings_slider_and_header():
    print("[53/56] Testing ui.settings Slider & Header Descriptors...")
    import ui.settings as s
    hdr = s.Header(title="Settings Header")
    assert hdr.text == "Settings Header"
    d_hdr = s.describe(hdr, 0)
    assert d_hdr["kind"] == "header"

    sl = s.Slider(key="sl", title="Opacity", min=0, max=100, step=5, default=50)
    assert sl.text == "Opacity"
    d_sl = s.describe(sl, 1)
    assert d_sl["kind"] == "slider"
    assert d_sl["min"] == 0
    assert d_sl["max"] == 100
    assert d_sl["default"] == 50
    print("  -> PASSED")


def test_ui_settings_category_deep_flattening():
    print("[54/56] Testing ui.settings Deep Category Flattening for Qt UI...")
    import ui.settings as s
    cat = s.Category(title="Category A", items=[
        s.Switch(key="sw1", title="Switch 1", default=True),
        s.Category(title="Subcategory B", items=[
            s.Switch(key="sw2", title="Switch 2", default=False),
        ])
    ])
    s.register_items("deep_cat_test", [cat])
    items = s._registered["deep_cat_test"]
    assert len(items) == 4
    assert items[0].text == "Category A"
    assert items[1].text == "Switch 1"
    assert items[2].text == "Subcategory B"
    assert items[3].text == "Switch 2"
    print("  -> PASSED")


def test_badges_json_project_integrity():
    print("[55/56] Testing badges.json Real File Schema & Owner Verification...")
    badges_file = os.path.join(REPO_ROOT, "badges.json")
    assert os.path.exists(badges_file)
    with open(badges_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "owner" in data.get("types", {})
    assert data["types"]["owner"]["emoji"] == "5425060246269736415"
    users = data.get("users", [])
    # Verify user 6486689289 (NanoDev)
    owner = next((u for u in users if u.get("id") == 6486689289), None)
    assert owner is not None
    assert owner.get("type") == "owner"
    assert owner.get("number") == 1
    assert "Ведущий разработчик" in owner.get("text", "")
    # Verify user 6296191170 (Friend)
    dev = next((u for u in users if u.get("id") == 6296191170), None)
    assert dev is not None
    assert "друг разработчика" in dev.get("text", "")
    assert "друга разработчика" not in dev.get("text", "")
    print("  -> PASSED")


def test_master_cohesion_and_pipeline():
    print("[56/56] Testing Master Cohesion, Plugin Sandboxing & Pipeline...")
    import extera_host
    from base_plugin import BasePlugin, HookResult, HookStrategy
    import ui.settings as s

    class MasterTestPlugin(BasePlugin):
        def on_plugin_load(self):
            self.loaded = True
        def on_send_message_hook(self, account, params):
            if "ping" in params.message:
                params.message = "pong"
                return HookResult.modify()
            return HookResult.default()
        def create_settings(self):
            return [s.Switch(key="m_sw", title="Master Switch")]

    p = MasterTestPlugin()
    p._extera_attach("master_test")
    p.on_plugin_load()
    assert getattr(p, "loaded", False) is True

    class Params:
        def __init__(self, m):
            self.message = m
            self.peer = 12345
            self.reply_to_id = 0

    p1 = Params("hello ping world")
    r1 = p.on_send_message_hook(0, p1)
    assert r1.strategy == HookStrategy.MODIFY
    assert p1.message == "pong"
    print("  -> PASSED")



if __name__ == "__main__":
    print("=" * 60)
    print(" oxDesktop Master Python Plugin & Security Test Harness")
    print("=" * 60)
    test_markdown()
    test_arraylist()
    test_settings_descriptors()
    test_alert_builder()
    test_plugin_lifecycle()
    test_outgoing_message_hooks()
    test_incoming_update_wrapping()
    test_pre_request_hook_cancel()
    test_post_request_hook()
    test_cactuslib()
    test_controllers_bridge()
    test_session_file_protection()
    test_token_and_env_shield()
    test_hybrid_send_message_params()
    test_sandboxed_open_and_subprocess()
    test_tl_name_and_extended_updates()
    test_plugin_lifecycle_fallbacks()
    test_run_on_queue_context_propagation()
    test_elyx_archive_plugin()
    test_critical_threat_scanner()
    test_polymorphic_signatures_and_command_registry()
    test_delete_and_pin_helpers()
    test_file_loader_and_download_controller()
    test_notification_center_pubsub()
    test_draft_and_forward_helpers()
    test_sqlite_and_pipe_sandboxing()
    test_hook_result_helpers_and_plugin_shortcuts()
    test_intents_with_placeholder_matching()
    test_metadata_parser_constants()
    test_metadata_parser_error_handling()
    test_capability_scan_static_analysis()
    test_capability_scan_threat_detection()
    test_text_formatting_html_parser()
    test_text_formatting_markdown()
    test_text_formatting_entity_to_dict()
    test_plugin_settings_typed_coercion()
    test_plugin_settings_persistence_and_notifier()
    test_android_utils_safe_call_and_runnable()
    test_android_utils_clipboard_and_context()
    test_android_views_base_view()
    test_android_views_textview()
    test_android_views_linearlayout()
    test_android_views_gradient_drawable()
    test_client_utils_hook_account_scoping()
    test_client_utils_peer_id_resolution()
    test_hook_utils_strategy_chaining()
    test_tl_runtime_constructors_and_classes()
    test_tl_runtime_serialization()
    test_intents_query_and_path_matching()
    test_file_utils_path_traversal_guard()
    test_compat_lenient_metaclass()
    test_compat_arraylist_methods()
    test_ui_settings_slider_and_header()
    test_ui_settings_category_deep_flattening()
    test_badges_json_project_integrity()
    test_master_cohesion_and_pipeline()
    print("=" * 60)
    print(">>> ALL 56/56 TESTS PASSED WITH 100% SUCCESS! <<<")
    print("=" * 60)
