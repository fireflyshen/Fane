"""Build three financial entry points from a private n8n export."""

import json
import sys
import uuid
from copy import deepcopy
from pathlib import Path

from organize import arrange, note

HERE = Path(__file__).parent
BILL = "3Wb33DhS6o6c2un7V-1z0"
BOOK = "bill-sync-20261005"
CHAT = "wdi3ZER_CXoaVm7cHRDGJ"
ALERT = "laPkUI5E-ux4FLqMI6-_M"
SCREEN = "BRt2kxO9Itpo4JtViPw9z"
KEEP = {BILL, BOOK, CHAT, ALERT, SCREEN}


def edge(name, index=0):
    return {"node": name, "type": "main", "index": index}


def connect(w, source, target, output=0):
    outputs = w["connections"].setdefault(source, {}).setdefault("main", [])
    while len(outputs) <= output:
        outputs.append([])
    outputs[output].append(edge(target))


def node(name, kind, parameters, version=2, **attributes):
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "fane/workflow/" + name)),
        "name": name,
        "type": "n8n-nodes-base." + kind,
        "typeVersion": version,
        "position": [0, 0],
        "parameters": parameters,
        **attributes,
    }


def code(name, source):
    return node(name, "code", {"jsCode": source})


def ssh(name, command, credentials):
    return node(
        name,
        "ssh",
        {"authentication": "privateKey", "command": command},
        1,
        credentials=deepcopy(credentials),
    )


def without_notes(w):
    result = deepcopy(w)
    for key in ("staticData", "meta"):
        if isinstance(result.get(key), str):
            result[key] = json.loads(result[key])
    result["nodes"] = [
        n for n in result["nodes"] if not n["type"].endswith(".stickyNote")
    ]
    return result


def inline(w, call, child):
    """Replace a call boundary with the unchanged child processing graph."""
    child = without_notes(child)
    trigger = next(
        n["name"]
        for n in child["nodes"]
        if n["type"].endswith(".executeWorkflowTrigger")
    )
    roots = child["connections"][trigger]["main"][0]
    outgoing = w["connections"].pop(call, {}).get("main", [[]])[0]
    names = {n["name"] for n in w["nodes"] if n["name"] != call}
    incoming = [n for n in child["nodes"] if n["name"] != trigger]
    assert not names.intersection(n["name"] for n in incoming), (
        "Inline node name collision"
    )
    w["nodes"] = [n for n in w["nodes"] if n["name"] != call] + incoming
    for groups in w["connections"].values():
        for kind, outputs in groups.items():
            for index, targets in enumerate(outputs):
                groups[kind][index] = [e for e in targets if e["node"] != call] + (
                    deepcopy(roots) if any(e["node"] == call for e in targets) else []
                )
    for name, groups in child["connections"].items():
        if name != trigger:
            w["connections"][name] = deepcopy(groups)
    for n in incoming:
        groups = w["connections"].get(n["name"], {})
        if not groups.get("main") and not any(k.startswith("ai_") for k in groups):
            w["connections"][n["name"]] = {"main": [deepcopy(outgoing)]}
    return w


def bills(source):
    w = without_notes(source[BILL])
    inline(w, "准备账单", source["bill-files-20261005"])
    w["nodes"] = [n for n in w["nodes"] if n["name"] != "BillFlow"]
    w["connections"].pop("BillFlow", None)
    imap = deepcopy(
        next(
            n
            for n in source["VnqBDFts2ZmAUrPxEAJo_"]["nodes"]
            if n["type"].endswith(".emailReadImap")
        )
    )
    w["nodes"].insert(0, imap)
    connect(w, imap["name"], "识别账单")
    for n in w["nodes"]:
        if n["name"] == "解密并准备":
            n["parameters"]["command"] = (
                "=/usr/local/bin/fa flow bill prepare '{{ $('识别账单').item.json.meta_b64 }}'"
            )
        elif n["name"] == "应用分类并生成订阅":
            n["parameters"]["command"] = (
                "=/usr/local/bin/fa flow bill finish '{{ $json.decisions_b64 || \"\" }}'"
            )
        elif n["name"] == "提交":
            n["parameters"]["command"] = (
                "=set -eu\ncd /root/.flow/data/account\ngit add --all\nif ! git diff --cached --quiet; then\n  git commit -m \"账单更新 {{ $now.toFormat('yyyy-MM-dd') }}\"\nfi\ngit push\n/usr/local/bin/fa flow report notice"
            )
        # Calls formerly saw the execution trigger as their input node.
        n["parameters"] = json.loads(
            json.dumps(n["parameters"], ensure_ascii=False).replace(
                "$('BillFlow')", "$('" + imap["name"] + "')"
            )
        )
    w["name"] = "账单入账"
    w["settings"]["errorWorkflow"] = ALERT
    incoming = source["VnqBDFts2ZmAUrPxEAJo_"].get("staticData")
    if isinstance(incoming, str):
        incoming = json.loads(incoming)
    if incoming:
        w["staticData"] = {**(w.get("staticData") or {}), **incoming}
    positions = {
        imap["name"]: (0, 0),
        "识别账单": (320, 0),
        "邮件有效": (640, 0),
        "支付宝": (960, 0),
        "下载微信账单": (1280, 320),
        "上传压缩包": (1600, 0),
        "解密并准备": (1920, 0),
        "检查账单结果": (2240, 0),
        "准备成功": (2560, 0),
        "需要分类": (2880, 0),
        "AI Agent": (3200, -320),
        "Google Gemini Chat Model": (3200, -80),
        "校验分类决策": (3520, -320),
        "应用分类并生成订阅": (3840, 0),
        "检查写入结果": (4160, 0),
        "提交": (4480, 0),
        "下载失败": (1920, 600),
        "账单处理失败": (2880, 600),
    }
    for n in w["nodes"]:
        n["position"] = list(positions[n["name"]])
    for title, text, names, color in [
        (
            "账单文件",
            "邮件 → 识别来源 → 下载、解密；仅保留有效账单。",
            list(positions)[:7],
            4,
        ),
        (
            "核算入账",
            "仅在需要时调用分类模型；校验成功后提交并记录账本变化。",
            list(positions)[7:16],
            5,
        ),
        (
            "失败出口",
            "下载或准备失败沿用原通知，停止后续写入。",
            list(positions)[16:],
            3,
        ),
    ]:
        w["nodes"].append(
            note(w, title, text, [n for n in w["nodes"] if n["name"] in names], color)
        )
    return w


def book(source):
    w = without_notes(source[BOOK])
    w["name"] = "账本更新"
    w["settings"]["errorWorkflow"] = ALERT
    old = without_notes(source["-woXn2NFfexoVljeyJCQ-"])
    monthly = {n["name"]: n for n in old["nodes"]}
    credentials = next(
        n["credentials"] for n in w["nodes"] if n["type"].endswith(".ssh")
    )
    schedule = deepcopy(
        next(
            n
            for n in source["kCVsuduDh0fBw6bnKoRCV"]["nodes"]
            if n["type"].endswith(".scheduleTrigger")
        )
    )
    schedule["name"] = "检查月报"
    schedule["parameters"] = {
        "rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}
    }
    callback = deepcopy(
        next(
            n
            for n in source["kCVsuduDh0fBw6bnKoRCV"]["nodes"]
            if n["type"].endswith(".webhook")
        )
    )
    callback["name"] = "账本更新回调"
    w["nodes"] = [n for n in w["nodes"] if n["name"] != "检查月报"]
    w["connections"].pop("检查月报", None)
    for n in w["nodes"]:
        if n["name"] == "验签并同步":
            n["parameters"]["command"] = (
                "=/usr/local/bin/fa flow sync '{{ $json.meta_b64 }}'"
            )
    w["connections"]["同步成功"]["main"][0] = [edge("记录账本变化")]
    w["nodes"] += [
        schedule,
        callback,
        ssh(
            "记录账本变化",
            "=/usr/local/bin/fa flow report notice {{ $json.body?.dryRun === true ? '--dry-run' : '' }}",
            credentials,
        ),
        ssh("待发月份", "=/usr/local/bin/fa flow report plan", credentials),
        code(
            "待发列表",
            "if ($json.code!==0) throw new Error('账本校验或月报检查失败');\nreturn JSON.parse($json.stdout).map(json=>({json}));",
        ),
        node("逐月处理", "splitInBatches", {"batchSize": 1, "options": {}}, 3),
        ssh(
            "领取月份",
            "=/usr/local/bin/fa flow report prepare --request-base64 '{{ Buffer.from(JSON.stringify($json)).toString(\"base64\") }}'",
            credentials,
        ),
        code(
            "领取月份结果",
            "if ($json.code!==0) throw new Error('月份领取失败');\nreturn [{json:JSON.parse($json.stdout)}];",
        ),
        node(
            "需要报告",
            "if",
            {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "strict",
                        "version": 2,
                    },
                    "conditions": [
                        {
                            "id": str(uuid.uuid4()),
                            "leftValue": "={{ $json.eligible }}",
                            "rightValue": "",
                            "operator": {
                                "type": "boolean",
                                "operation": "true",
                                "singleValue": True,
                            },
                        }
                    ],
                    "combinator": "and",
                },
                "options": {},
            },
            2.2,
        ),
    ]
    agent = deepcopy(monthly["AI Agent"])
    agent["parameters"]["text"] = "=" + (HERE / "report.txt").read_text()
    agent["onError"] = "continueErrorOutput"
    agent.update(retryOnFail=True, maxTries=3, waitBetweenTries=2000)
    model = deepcopy(monthly["Google Gemini Chat Model"])
    context_node = code(
        "分析上下文",
        "const original=$('领取月份结果').item.json;\nreturn [{json:{...original,...$json,tries:($json.tries||0)+1}}];",
    )
    renderer = code(
        "报告",
        (HERE / "report.js").read_text()
        + "\nconst context=$('分析上下文').item.json;\ntry {\n const rendered=report($json.output ?? $json.text ?? '',context);\n return [{json:{...context,report:rendered}}];\n} catch(error) {\n if(context.tries>=3) throw error;\n return [{json:{...context,validationFeedback:String(error.message).slice(0,300)}}];\n}",
    )
    renderer["onError"] = "continueErrorOutput"
    valid = node(
        "报告有效",
        "if",
        deepcopy(next(n for n in w["nodes"] if n["name"] == "需要报告")["parameters"]),
        2.2,
    )
    valid["parameters"]["conditions"]["conditions"][0]["leftValue"] = (
        "={{ !!$json.report }}"
    )
    save = ssh(
        "保存报告",
        "=/usr/local/bin/fa flow report store --request-base64 '{{ Buffer.from(JSON.stringify({analysisMonth:$json.analysisMonth,claimToken:$json.claimToken,report:$json.report})).toString(\"base64\") }}'",
        credentials,
    )
    ready = code(
        "保存结果",
        "if ($json.code!==0) throw new Error('报告保存失败');\nconst r=JSON.parse($json.stdout);\nif (!r.stored) throw new Error('账本在分析期间改变，报告已撤销，待稳定后重新生成');\nreturn [{json:r}];",
    )
    ready["onError"] = "continueErrorOutput"
    begin = ssh(
        "准备发送",
        "=/usr/local/bin/fa flow report begin --request-base64 '{{ Buffer.from(JSON.stringify($json)).toString(\"base64\") }}'",
        credentials,
    )
    body = code(
        "邮件内容",
        "if ($json.code!==0) throw new Error('邮件领取失败，禁止重发');\nconst r=JSON.parse($json.stdout);\nif (!r.email_html) throw new Error('发送前账本改变，报告已撤销，等待重新生成');\nreturn [{json:r}];",
    )
    email = deepcopy(monthly["Send email"])
    email["name"] = "发送月报"
    email["onError"] = "continueErrorOutput"
    email["parameters"].update(
        subject="={{ $json.mail_subject }}",
        html="={{ $json.email_html }}",
        text="={{ $json.email_text }}",
        emailFormat="both",
    )
    receipt = code(
        "发送回执",
        "const claim=$('邮件内容').item.json;\nreturn [{json:{analysisMonth:claim.analysisMonth,claimToken:claim.claimToken,messageId:$json.messageId,accepted_count:($json.accepted||[]).length,rejected_count:($json.rejected||[]).length}}];",
    )
    sent = ssh(
        "完成月报",
        "=/usr/local/bin/fa flow report sent --request-base64 '{{ Buffer.from(JSON.stringify($json)).toString(\"base64\") }}'",
        credentials,
    )
    done = code(
        "完成结果",
        "if ($json.code!==0) throw new Error('邮件已发送但回执保存失败，请人工核对，禁止重发');\nreturn [{json:JSON.parse($json.stdout)}];",
    )
    release = ssh(
        "保留发送状态",
        '=/usr/local/bin/fa flow report release --request-base64 \'{{ Buffer.from(JSON.stringify({analysisMonth:$("领取月份结果").item.json.analysisMonth,claimToken:$("领取月份结果").item.json.claimToken})).toString("base64") }}\'',
        credentials,
    )
    fail = code(
        "报告失败",
        "throw new Error('月报生成或发送失败，请检查本次执行；送达不确定的邮件不会自动重发');",
    )
    w["nodes"] += [
        context_node,
        agent,
        model,
        renderer,
        valid,
        save,
        ready,
        begin,
        body,
        email,
        receipt,
        sent,
        done,
        release,
        fail,
    ]
    for a, b in [
        ("账本更新回调", "记录账本变化"),
        ("检查月报", "待发月份"),
        ("待发月份", "待发列表"),
        ("待发列表", "逐月处理"),
        ("领取月份", "领取月份结果"),
        ("领取月份结果", "需要报告"),
        ("需要报告", "分析上下文"),
        ("分析上下文", "AI Agent"),
        ("AI Agent", "报告"),
        ("报告", "报告有效"),
        ("报告有效", "保存报告"),
        ("保存报告", "保存结果"),
        ("保存结果", "准备发送"),
        ("准备发送", "邮件内容"),
        ("邮件内容", "发送月报"),
        ("发送月报", "发送回执"),
        ("发送回执", "完成月报"),
        ("完成月报", "完成结果"),
        ("完成结果", "逐月处理"),
        ("保留发送状态", "报告失败"),
    ]:
        connect(w, a, b)
    connect(w, "报告有效", "分析上下文", 1)
    connect(w, "逐月处理", "领取月份", 1)
    connect(w, "需要报告", "逐月处理", 1)
    for n in [agent, renderer, ready, email]:
        connect(w, n["name"], "保留发送状态", 1)
    w["connections"][model["name"]] = {
        "ai_languageModel": [
            [{"node": agent["name"], "type": "ai_languageModel", "index": 0}]
        ]
    }
    positions = {
        "GitHub": (0, -600),
        "读取原始请求": (320, -600),
        "验签并同步": (640, -600),
        "同步结果": (960, -600),
        "回应 GitHub": (1280, -820),
        "同步成功": (1280, -600),
        "记录账本变化": (1600, -600),
        "账本更新回调": (1280, -360),
        "检查月报": (0, 0),
        "待发月份": (320, 0),
        "待发列表": (640, 0),
        "逐月处理": (960, 0),
        "领取月份": (1280, 0),
        "领取月份结果": (1600, 0),
        "需要报告": (1920, 0),
        "AI Agent": (2240, 0),
        "Google Gemini Chat Model": (2240, 240),
        "报告": (2560, 0),
        "保存报告": (2880, 0),
        "保存结果": (3200, 0),
        "准备发送": (3520, 0),
        "邮件内容": (3840, 0),
        "发送月报": (4160, 0),
        "发送回执": (4480, 0),
        "完成月报": (4800, 0),
        "完成结果": (5120, 0),
        "保留发送状态": (3840, 620),
        "报告失败": (4160, 620),
    }
    positions.update({"分析上下文": (1920, 480), "报告有效": (2560, 480)})
    w["nodes"] = [n for n in w["nodes"] if not n["type"].endswith(".stickyNote")]
    for n in w["nodes"]:
        n["position"] = list(positions[n["name"]])
    for title, text, names, color in [
        (
            "同步",
            "GitHub 回调先同步 Fava，再记录变化；立即回应，不等待模型。",
            ["GitHub", "记录账本变化", "回应 GitHub", "账本更新回调"],
            4,
        ),
        (
            "领取",
            "每 5 分钟检查；更新稳定 10 分钟后，按月串行领取。",
            ["检查月报", "需要报告"],
            5,
        ),
        (
            "分析",
            "完整账本核算；修订保留原行动目标。",
            ["AI Agent", "Google Gemini Chat Model", "报告", "保存结果"],
            6,
        ),
        (
            "投递",
            "发送前锁定状态，SMTP 回执落盘；不确定时禁止自动重发。",
            ["准备发送", "完成结果"],
            4,
        ),
        (
            "失败",
            "释放未生成的任务；已开始投递的状态保留供人工核对。",
            ["保留发送状态", "报告失败"],
            3,
        ),
    ]:
        w["nodes"].append(
            note(w, title, text, [n for n in w["nodes"] if n["name"] in names], color)
        )
    return w


def chat(source):
    w = without_notes(source[CHAT])
    query = next(
        n
        for n in source["6d9MO4WLPj57HygGGuR2o"]["nodes"]
        if n["type"].endswith(".httpRequest")
    )
    tool = next(n for n in w["nodes"] if n["name"] == "query_ledger")
    tool["type"] = "n8n-nodes-base.httpRequestTool"
    tool["typeVersion"] = 4.3
    tool["parameters"] = deepcopy(query["parameters"])
    tool["parameters"].update(
        toolDescription="查询 Beancount 完整账本。财务问题必须查询后回答。开始、结束日期必须为 YYYY-MM-DD，范围最多 366 天；内部转账和还款不重复计为收支。",
        jsonBody="={{ {start_date:$fromAI('start_date','查询开始日期 YYYY-MM-DD','string'),end_date:$fromAI('end_date','查询结束日期 YYYY-MM-DD','string'),max_transactions:200} }}",
    )
    tool["parameters"]["options"] = {"timeout": 30000}
    w["settings"]["errorWorkflow"] = ALERT
    return arrange(w)


def project_commands(w):
    """Replace retired script entry points with the installed project CLI."""
    if not w:
        return w
    for n in w["nodes"]:
        if not n["type"].endswith(".ssh"):
            continue
        if "command" not in n["parameters"]:
            continue
        command = n["parameters"].get("command", "")
        for source, target in [
            (
                "/usr/bin/python3 /root/.flow/runtime/libexec/bill.py",
                "/usr/local/bin/fa flow bill",
            ),
            (
                "/usr/bin/python3 /root/.flow/runtime/libexec/sync.py",
                "/usr/local/bin/fa flow sync",
            ),
            (
                "/usr/bin/python3 /root/.flow/runtime/libexec/monthly-report.py",
                "/usr/local/bin/fa flow report",
            ),
        ]:
            command = command.replace(source, target)
        if n["name"] == "提交":
            command = "=/usr/local/bin/fa flow commit"
        n["parameters"]["command"] = command
    return w


def build(pairs):
    indexed = {p["draft"]["id"]: p for p in pairs}
    if "-woXn2NFfexoVljeyJCQ-" not in indexed:
        assert KEEP.issubset(indexed), "Missing financial workflow"
        output = [deepcopy(indexed[wid]) for wid in (BILL, BOOK, CHAT, SCREEN, ALERT)]
        for pair in output:
            for w in pair.values():
                project_commands(w)
                if w and w["id"] == BOOK:
                    for n in w["nodes"]:
                        if n["name"] == "AI Agent":
                            n["parameters"]["text"] = (
                                "=" + (HERE / "report.txt").read_text()
                            )
                        if n["name"] == "报告":
                            existing = n["parameters"]["jsCode"]
                            tail = existing[existing.index("\nconst context=") :]
                            n["parameters"]["jsCode"] = (
                                HERE / "report.js"
                            ).read_text() + tail
        metadata = {
            BILL: {"name": "账单入账", "tags": ["财务", "账单"]},
            BOOK: {"name": "账本更新", "tags": ["财务", "同步", "月报"]},
            CHAT: {"name": "账单问答", "tags": ["财务", "查询"]},
            SCREEN: {"name": "屏幕时间周报", "tags": ["生活", "屏幕时间", "未启用"]},
            ALERT: {"name": "执行告警", "tags": ["运维", "告警"]},
        }
        return {
            "workflows": output,
            "metadata": metadata,
            "remove": [
                {"id": p["draft"]["id"], "name": p["draft"]["name"]}
                for p in pairs
                if p["draft"]["id"] not in KEEP
            ],
        }
    output = []
    for identifier, builder in [(BILL, bills), (BOOK, book), (CHAT, chat)]:
        result = {}
        for key in ("draft", "published"):
            source = {wid: p[key] or p["draft"] for wid, p in indexed.items()}
            result[key] = project_commands(builder(source))
        output.append(result)
    for identifier in (SCREEN, ALERT):
        pair = deepcopy(indexed[identifier])
        for w in pair.values():
            if w:
                for key in ("staticData", "meta"):
                    if isinstance(w.get(key), str):
                        w[key] = json.loads(w[key])
                if identifier == ALERT:
                    w["name"] = "执行告警"
        if identifier == ALERT:
            pair["published"] = deepcopy(pair["draft"])
        output.append(pair)
    metadata = {
        BILL: {"name": "账单入账", "tags": ["财务", "账单"]},
        BOOK: {"name": "账本更新", "tags": ["财务", "同步", "月报"]},
        CHAT: {"name": "账单问答", "tags": ["财务", "查询"]},
        SCREEN: {"name": "屏幕时间周报", "tags": ["生活", "屏幕时间", "未启用"]},
        ALERT: {"name": "执行告警", "tags": ["运维", "告警"]},
    }
    removed = [
        {
            "id": p["draft"]["id"],
            "name": p["draft"]["name"],
            "reason": "已合并" if p["draft"]["active"] else "未启用且无独立使用记录",
        }
        for p in pairs
        if p["draft"]["id"] not in KEEP
    ]
    return {"workflows": output, "metadata": metadata, "remove": removed}


if __name__ == "__main__":
    data = build(json.loads(Path(sys.argv[1]).read_text()))
    path = Path(sys.argv[2])
    path.write_text(json.dumps(data, ensure_ascii=False))
    path.chmod(0o600)
    print(
        json.dumps(
            {
                "retained": [p["draft"]["name"] for p in data["workflows"]],
                "removed": data["remove"],
            },
            ensure_ascii=False,
        )
    )
