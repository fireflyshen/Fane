const assert = require("node:assert/strict");
const fs = require("node:fs");
const report = require("./report");
const copy = (x) => JSON.parse(JSON.stringify(x));
const facts = {
  period: { start: "2026-09-01", end: "2026-09-30", days_inclusive: 30 },
  statistics: { transaction_count: 23, truncated: false },
  totals: {
    income: { gross: { CNY: "12000" }, reversals: {}, net: { CNY: "12000" } },
    expenses: {
      gross: { CNY: "5800" },
      refunds: { CNY: "300" },
      net: { CNY: "5500" },
    },
  },
  income_by_account: { "Income:Salary": { CNY: "12000" } },
  expenses_by_account: {
    "Expenses:Rent": { CNY: "3000" },
    "Expenses:Food": { CNY: "1500" },
    "Expenses:Shopping": { CNY: "600" },
    "Expenses:Transport": { CNY: "400" },
  },
  account_counts: {
    "Income:Salary": 1,
    "Expenses:Rent": 1,
    "Expenses:Food": 12,
    "Expenses:Shopping": 4,
    "Expenses:Transport": 5,
  },
  balance_sheet_changes: {},
  top_expenses: {
    CNY: [
      {
        date: "2026-09-02",
        payee: "月租",
        narration: "住房支出",
        amount: "3000",
        currency: "CNY",
        recognition: "cash",
      },
      {
        date: "2026-09-12",
        payee: "示例商户",
        narration: "购置生活用品",
        amount: "600",
        currency: "CNY",
        recognition: "cash",
      },
    ],
  },
  frequent_payees: { CNY: [{ payee: "示例餐厅", count: 8, amount: "980" }] },
  warnings: [],
};
const previous = copy(facts);
previous.period = {
  start: "2026-08-01",
  end: "2026-08-31",
  days_inclusive: 31,
};
previous.totals.expenses.net.CNY = "6000";
const context = {
  analysisMonth: "2026-09",
  previousMonth: "2026-08",
  facts,
  previousFacts: previous,
  previousActions: [],
};
const response = {
  summary:
    "本月结余 6,500 元，支出较上月下降 500 元。下月优先维持餐饮预算，并核对购物退款。",
  insights: [
    {
      title: "支出有所回落",
      detail: "净支出环比下降 8.3%。保持已有节奏，先确认购物退款是否全部入账。",
      evidence: "本月净支出 5,500 CNY，上月 6,000 CNY；退款抵减 300 CNY。",
    },
  ],
  observations: [
    {
      title: "餐饮适合设月度上限",
      detail:
        "支出分散在多次消费，可先按本月水平设上限，再观察是否影响正常用餐。",
      evidence: "Expenses:Food 净额 1,500 CNY，共 12 笔。",
    },
  ],
  evaluations: [],
  new_actions: [
    {
      title: "维持餐饮预算",
      metric: "Expenses:Food / 净额",
      category: "immediate",
      operator: "<=",
      baseline_value: 1500,
      target_value: 1500,
      unit: "CNY",
      weight: 30,
      reason: "以本月正常用餐支出为上限，不压缩必要消费。",
    },
    {
      title: "购物先列清单",
      metric: "Expenses:Shopping / 净额",
      category: "immediate",
      operator: "<=",
      baseline_value: 600,
      target_value: 600,
      unit: "CNY",
      weight: 25,
      reason: "先列需求再购买，出现必要大件时调整预算。",
    },
    {
      title: "维持交通预算",
      metric: "Expenses:Transport / 净额",
      category: "immediate",
      operator: "<=",
      baseline_value: 400,
      target_value: 400,
      unit: "CNY",
      weight: 20,
      reason: "本月水平作为观察基线，不影响正常出行。",
    },
    {
      title: "保持工资入账核对",
      metric: "Income:Salary / 交易次数",
      category: "long_term",
      operator: ">=",
      baseline_value: 1,
      target_value: 1,
      unit: "次",
      weight: 15,
      reason: "每月核对工资到账与账本，遇到账期变化单独说明。",
    },
    {
      title: "持续核对房租记录",
      metric: "Expenses:Rent / 交易次数",
      category: "long_term",
      operator: "=",
      baseline_value: 1,
      target_value: 1,
      unit: "次",
      weight: 10,
      reason: "核对固定支出的记录完整性。",
    },
  ],
};
let checks = 0;
function check(name, fn) {
  fn();
  checks++;
  console.log("PASS " + name);
}
check("固定事实、环比与HTML/纯文本", () => {
  const r = report(JSON.stringify(response), context);
  assert.match(r.email_html, /6,500.00 CNY/);
  assert.match(r.email_html, /-500.00 CNY/);
  assert.match(r.email_text, /退款抵减 300.00 CNY/);
  assert.equal(r.template_version, 2);
  assert.ok(Buffer.byteLength(r.email_html) < 90000);
});
check("零收入与缺失上月", () => {
  const c = copy(context);
  c.facts.totals.income.net.CNY = "0";
  c.previousFacts = null;
  const r = report(JSON.stringify(response), c);
  assert.match(r.email_text, /结余率：不适用/);
  assert.match(r.email_text, /暂不做环比/);
});
check("负收入、负支出及退款占比不误导", () => {
  const c = copy(context);
  c.facts.totals.income.net.CNY = "-10";
  c.facts.totals.expenses.net.CNY = "-50";
  c.facts.expenses_by_account["Expenses:Refund"] = { CNY: "-5550" };
  const r = report(JSON.stringify(response), c);
  assert.match(r.email_text, /占比不适用/);
  assert.match(r.email_text, /结余率：不适用/);
});
check("多币种分别核算", () => {
  const c = copy(context);
  c.facts.totals.expenses.net.USD = "20";
  c.facts.expenses_by_account["Expenses:Other"] = { USD: "20" };
  const r = report(JSON.stringify(response), c);
  assert.match(r.email_text, /20.00 USD/);
  assert.match(r.email_text, /未换算或合计/);
});
check("HTML转义与长字符串", () => {
  const d = copy(response);
  d.summary = '<script>alert("x")</script>';
  const r = report(JSON.stringify(d), context);
  assert.ok(!r.email_html.includes("<script>"));
  assert.match(r.email_html, /&lt;script&gt;/);
});
check("金额精度与极小日均值", () => {
  const c = copy(context);
  c.facts.totals.income.net.CNY = "9007199254740993.01";
  c.facts.totals.expenses.net.CNY = "0.00000001";
  const r = report(JSON.stringify(response), c);
  assert.match(r.email_text, /9,007,199,254,740,993.01 CNY/);
  assert.match(r.email_text, /日均净支出：0.00 CNY/);
});
check("禁止缺复盘、篡改基线、错误权重和虚构次数", () => {
  const c = copy(context);
  c.previousActions = [{ action_id: "a" }];
  assert.throws(() => report(JSON.stringify(response), c));
  for (const [key, value] of [
    ["baseline_value", 0],
    ["weight", 22],
    ["unit", "EUR"],
  ]) {
    const d = copy(response);
    d.new_actions[0][key] = value;
    assert.throws(() => report(JSON.stringify(d), context));
  }
  const d = copy(response);
  d.new_actions[3].target_value = 1.5;
  assert.throws(() => report(JSON.stringify(d), context));
});
check("未知复盘不计零分与覆盖率", () => {
  const c = copy(context);
  c.previousActions = [
    {
      action_id: "a",
      title: "餐饮",
      metric: "Expenses:Food / 净额",
      operator: "<=",
      target_value: 1600,
      unit: "CNY",
      weight: 60,
    },
    {
      action_id: "b",
      title: "储备",
      metric: "缺少资产数据",
      operator: ">=",
      target_value: 1000,
      unit: "CNY",
      weight: 40,
    },
  ];
  const d = copy(response);
  d.evaluations = [
    {
      action_id: "a",
      actual_value: 1500,
      score: 100,
      status: "达成",
      evidence: "本月净额1500，低于上限1600。",
    },
    {
      action_id: "b",
      actual_value: null,
      score: null,
      status: "信息不足",
      evidence: "没有完整资产余额。",
    },
  ];
  const r = report(JSON.stringify(d), c);
  assert.match(r.email_text, /100 分；权重覆盖 60%/);
  d.evaluations[0].actual_value = 1700;
  assert.throws(() => report(JSON.stringify(d), c));
});
check("无收入与支出的转账月份仍可展示", () => {
  const c = copy(context);
  c.facts.totals.income.net = {};
  c.facts.totals.expenses.net = {};
  c.facts.balance_sheet_changes = { "Assets:Bank": { CNY: "0" } };
  const r = report(JSON.stringify(response), c);
  assert.match(r.email_text, /净收入：0.00 CNY/);
});
check("补账修订更新核算并保留原目标与基线", () => {
  const c = copy(context);
  c.reportMode = "revision";
  c.revision = 2;
  c.retainedActions = copy(response.new_actions);
  c.facts.expenses_by_account["Expenses:Food"].CNY = "1800";
  c.facts.totals.expenses.net.CNY = "5800";
  const d = copy(response);
  d.new_actions = [];
  const r = report(JSON.stringify(d), c);
  assert.match(r.email_text, /修订 2/);
  assert.match(r.email_text, /5,800.00 CNY/);
  assert.match(r.email_text, /制定时基线 1500/);
  assert.deepEqual(r.new_actions, response.new_actions);
});
if (process.argv.includes("--preview")) {
  fs.mkdirSync("output/playwright", { recursive: true });
  const r = report(JSON.stringify(response), context);
  fs.writeFileSync(
    "output/playwright/report.html",
    r.email_html.replace("个人财务 &nbsp;", "示例数据 &nbsp;"),
  );
  fs.writeFileSync(
    "output/playwright/report-no-css.html",
    r.email_html
      .replace(/<style>[\s\S]*?<\/style>/, "")
      .replace("个人财务 &nbsp;", "示例数据 &nbsp;"),
  );
  const c = copy(context);
  c.facts.top_expenses.CNY[0].payee = "LongMerchantIdentifier".repeat(20);
  c.facts.expenses_by_account["Expenses:" + "LongCategory".repeat(20)] = {
    CNY: "2",
  };
  fs.writeFileSync(
    "output/playwright/report-long.html",
    report(JSON.stringify(response), c).email_html,
  );
  fs.writeFileSync(
    "/tmp/report-optimize/fixture.json",
    JSON.stringify({ context, response }),
  );
}
console.log(`${checks} checks passed`);
