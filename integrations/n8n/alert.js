// Only failures in business validation reach the email node.
const execution = $json.execution || {};
const workflow = $json.workflow || {};
const error = execution.error || $json.trigger?.error || {};
const message = String(error.message || error.description || "未提供错误信息");
const nodeName = execution.lastNodeExecuted || error.node?.name || "未知节点";
const operational =
    /WorkflowCrashedError|WorkflowActivationError|out.of.memory|heap|ECONN\w*|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|socket|timed?\s*out|timeout|network|fetch failed|connection|rate.?limit|quota|too many requests|service unavailable|bad gateway|authentication|unauthorized|credential|permission denied|EACCES|ENOSPC|SSH|SMTP|IMAP|账本在分析期间改变|发送前账本改变|报告保存失败|月份领取失败|邮件领取失败/i;
const businessNodes = {
    "3Wb33DhS6o6c2un7V-1z0": ["识别账单", "校验分类决策", "检查写入结果"],
    "bill-sync-20261005": ["待发列表", "报告"],
    BRt2kxO9Itpo4JtViPw9z: ["准备请求与质量检查", "生成邮件与记录"],
};
if ($json.trigger || operational.test(`${error.name || ""} ${message}`))
    return [];
const tagged = message.startsWith("[BUSINESS] ");
if (!tagged && !(businessNodes[workflow.id] || []).includes(nodeName))
    return [];
const detail = tagged ? message.slice("[BUSINESS] ".length) : message;
const esc = (value) =>
    String(value ?? "").replace(
        /[&<>"']/g,
        (ch) =>
            ({
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#39;",
            })[ch],
    );
const workflowName = workflow.name || "未知工作流";
const html =
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"></head>' +
    '<body style="color:#37352f;font:14px/1.6 sans-serif"><main style="max-width:760px;margin:auto;padding:24px">' +
    '<h1 style="font-size:24px">n8n 业务处理失败</h1>' +
    "<p>工作流：" +
    esc(workflowName) +
    "</p><p>失败节点：" +
    esc(nodeName) +
    "</p>" +
    "<p>错误信息：" +
    esc(detail) +
    "</p><p>执行编号：" +
    esc(execution.id || "数据不足") +
    "</p>" +
    (execution.url
        ? '<p><a href="' + esc(execution.url) + '">打开失败执行</a></p>'
        : "") +
    "</main></body></html>";
return [{ json: { subject: "n8n 业务失败 · " + workflowName, html } }];
