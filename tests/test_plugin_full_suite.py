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
    print("[1/19] Testing Markdown & Entity Parsing...")
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
    print("[2/19] Testing ArrayList & Java Bridge Types...")
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
    print("[3/19] Testing Settings Components & Dynamic Descriptors...")
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

    cat = s.Category(title="Category Header")
    assert cat.text == "Category Header"

    cp = s.ColorPicker(key="col", title="Color", default="#FF0000")
    assert cp.default == "#FF0000"
    desc_cp = s.describe(cp, 4)
    assert desc_cp["default"] == "#FF0000"

    mc = s.MultiChoice(key="mc", title="Multi", items=["Opt1", "Opt2"], default=[0])
    assert mc.items == ["Opt1", "Opt2"]
    desc_mc = s.describe(mc, 5)
    assert desc_mc["items"] == ["Opt1", "Opt2"]
    print("  -> PASSED")


def test_alert_builder():
    print("[4/19] Testing AlertDialogBuilder & CamelCase Aliases...")
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
    print("[5/19] Testing Plugin Lifecycle (Load, Unload, Settings, Deletion)...")
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
    print("[6/19] Testing Outgoing Message Interception & Modification...")
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
    print("[7/19] Testing Incoming Update TL Wrapping...")
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
    print("[8/19] Testing Pre-Request Hook Cancellation (Ghost Mode)...")
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
    print("[9/19] Testing Post-Request Hook Dispatch...")
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
    print("[10/19] Testing CactusLib (@command, Command context, DB)...")
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
    print("[11/19] Testing Controllers Bridge (Messages, Contacts, Media, SendHelper)...")
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
    print("[12/19] Testing Security: Session & Credential File Protection...")
    assert file_utils.read_file("tdata/key_datas") is None
    assert file_utils.read_file_bytes("tdata/D877F783D5D3EF8C0") is None
    assert file_utils.write_file("tdata/settings0", "hack") is False
    assert file_utils.delete_file("tdata/key_datas") is False
    assert file_utils.list_dir("tdata") == []
    print("  -> PASSED")


def test_token_and_env_shield():
    print("[13/19] Testing Security: Environment & Token Shielding...")
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
    print("[14/19] Testing Hybrid SendMessageParams & _ReplyStub...")
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
    print("[15/19] Testing Sandboxed builtins.open, os.remove, subprocess inside Plugin Context...")
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
    print("[16/19] Testing TLName Single-Dispatch & Extended Update Wrapping...")
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
    print("[17/19] Testing BasePlugin Lifecycle Fallbacks (on_load, on_unload)...")
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
    print("[18/19] Testing run_on_queue Context Propagation...")
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
    print("[19/19] Testing Elyx/EAF Multi-File Archive Plugin Loading...")
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
        extera_host._install_plugin_importer()
        extera_host._activate(record)

        assert record.instance is not None
        assert record.instance._val == 42
        extera_host._deactivate(record)
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
    print("=" * 60)
    print(">>> ALL 19/19 TESTS PASSED WITH 100% SUCCESS! <<<")
    print("=" * 60)
