const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const source = fs.readFileSync(path.join(__dirname, "alert.js"), "utf8");
const alert = new Function("$json", source);
const bill = "3Wb33DhS6o6c2un7V-1z0";
const book = "bill-sync-20261005";
const payload = (id, node, message, name = "Error") => ({
  workflow: { id, name: "测试流程" },
  execution: {
    id: "fixture",
    lastNodeExecuted: node,
    error: { name, message },
  },
});
const muted = [
  {
    workflow: { id: bill },
    trigger: {
      error: {
        name: "WorkflowActivationError",
        message: "IMAP disconnected",
      },
    },
  },
  payload(
    bill,
    "AI Agent",
    "Workflow did not finish, possible out-of-memory issue",
    "WorkflowCrashedError",
  ),
  payload(bill, "校验分类决策", "ETIMEDOUT"),
  payload(bill, "解密并准备", "SSH authentication failed"),
  payload(book, "报告失败", "月报生成或发送失败，请检查本次执行"),
  payload(
    book,
    "报告失败",
    "[BUSINESS] 账本在分析期间改变，报告已撤销，待稳定后重新生成",
  ),
  payload(book, "报告失败", "[BUSINESS] 报告保存失败"),
  payload(book, "报告失败", "[BUSINESS] fetch failed"),
  payload(book, "发送月报", "SMTP timeout"),
  payload(bill, "AI Agent", "429 quota exceeded"),
  payload(bill, "上传压缩包", "connection reset"),
  payload("unknown", "未知节点", "unknown"),
];
for (const value of muted) assert.deepEqual(alert(value), []);
const business = [
  payload(bill, "账单业务失败", "[BUSINESS] 账单解析或入账失败（alipay）"),
  payload(bill, "校验分类决策", "AI 分类结果不是有效 decisions JSON"),
  payload(bill, "检查写入结果", "账本写入失败: classify"),
  payload(book, "报告失败", "[BUSINESS] 行动金额基线与账本不一致"),
  payload(book, "待发列表", "账本校验或月报检查失败"),
];
for (const value of business) {
  const result = alert(value);
  assert.equal(result.length, 1);
  assert.match(result[0].json.subject, /^n8n 业务失败/);
  assert.ok(!result[0].json.html.includes("[BUSINESS]"));
}
assert.ok(
  alert(
    payload(bill, "校验分类决策", "<script>bad</script>"),
  )[0].json.html.includes("&lt;script&gt;"),
);

// Exercise the same node source that the workflow generator deploys.
const python = `import json,sys
sys.path.insert(0, 'integrations/n8n')
from workflows import business_alerts,BILL,BOOK
b={'id':BILL,'nodes':[],'connections':{'准备成功':{'main':[[],[]]}}}
r={'id':BOOK,'nodes':[{'name':'报告失败','parameters':{}}]}
business_alerts(b); business_alerts(b); business_alerts(r)
assert len(b['nodes'])==1 and len(b['connections']['准备成功']['main'][1])==1
print(json.dumps([b['nodes'][0]['parameters']['jsCode'],r['nodes'][0]['parameters']['jsCode']]))`;
const [billSource, reportSource] = JSON.parse(
  execFileSync("python3", ["-c", python], {
    cwd: path.join(__dirname, "../.."),
    encoding: "utf8",
  }),
);
const billFailure = new Function("$json", billSource);
for (const stage of ["unzip", "import", "extract"]) {
  assert.throws(() => billFailure({ ok: false, stage }), /\[BUSINESS\]/);
}
assert.deepEqual(billFailure({ ok: false, stage: "download" }), []);
assert.deepEqual(billFailure({ ok: true, stage: "import" }), []);
assert.throws(
  () =>
    billFailure({
      ok: false,
      stage: "import",
      provider: "alipay",
      error:
        "来源 wechat（wechat），文件 bill.xlsx: 交易类型 包含不支持的值: 新类型",
    }),
  (error) =>
    error.message.includes("来源 wechat（wechat）") &&
    error.message.includes("新类型") &&
    !error.message.includes("alipay"),
);
const reportFailure = new Function("$", reportSource);
let forwarded;
try {
  reportFailure((name) => ({
    item: {
      json: name === "报告" ? { error: { message: "报告金额校验失败" } } : {},
    },
  }));
} catch (error) {
  forwarded = error.message;
}
assert.equal(alert(payload(book, "报告失败", forwarded)).length, 1);
try {
  reportFailure(() => {
    throw new Error("No paired item");
  });
} catch (error) {
  forwarded = error.message;
}
assert.deepEqual(alert(payload(book, "报告失败", forwarded)), []);
console.log(
  "Business alert checks passed: operational failures muted; business failures retained.",
);
