/* Deterministic email renderer. Embedded unchanged in the n8n Code node. */
function report(raw, context) {
  const fail = message => { throw new Error(`月报校验失败：${message}`); };
  const object = (x, keys) => x && !Array.isArray(x) && typeof x === 'object' && Object.keys(x).every(k => keys.includes(k)) && keys.every(k => Object.hasOwn(x, k));
  const string = (x, max) => typeof x === 'string' && x.trim().length > 0 && x.length <= max;
  const finite = x => typeof x === 'number' && Number.isFinite(x);
  if (typeof raw !== 'string' || raw.length > 30000) fail('响应长度或类型异常');
  let data;
  try { data = JSON.parse(raw.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '')); }
  catch { fail('需要合法 JSON'); }
  if (!object(data, ['summary','insights','observations','evaluations','new_actions']) || !string(data.summary, 120)) fail('报告结构或概述异常');
  for (const [key, count, length] of [['insights',3,100],['observations',2,80]]) {
    if (!Array.isArray(data[key]) || data[key].length > count) fail(`${key}过长`);
    for (const x of data[key]) if (!object(x,['title','detail','evidence']) || !string(x.title,20) || !string(x.detail,length) || !string(x.evidence,120)) fail(`${key}格式异常`);
  }
  const facts = context.facts, previous = context.previousFacts;
  if (!facts?.totals || !facts.period || facts.period.start.slice(0,7) !== context.analysisMonth || facts.statistics.truncated) fail('缺少完整的核算数据');
  const economicCurrencies = [...new Set([...Object.keys(facts.totals.income.net), ...Object.keys(facts.totals.expenses.net)])];
  const currencies = (economicCurrencies.length ? economicCurrencies : [...new Set(Object.values(facts.balance_sheet_changes || {}).flatMap(v=>Object.keys(v)))]).sort();
  const metricValue = (metric, unit) => {
    const match = metric.match(/^((?:Income|Expenses):\S+) \/ (净额|交易次数)$/);
    if (!match) return undefined;
    if (match[2] === '交易次数') return unit === '次' ? facts.account_counts?.[match[1]] : undefined;
    const accounts = match[1].startsWith('Income:') ? facts.income_by_account : facts.expenses_by_account;
    return Object.hasOwn(accounts[match[1]] || {},unit) ? Number(accounts[match[1]][unit]) : undefined;
  };
  const plans = context.previousActions || [];
  const revision = context.reportMode === 'revision' || Number(context.revision || 1) > 1;
  const retained = revision && Array.isArray(context.retainedActions) && context.retainedActions.length === 5;
  if (retained) data.new_actions = JSON.parse(JSON.stringify(context.retainedActions));
  if (!Array.isArray(data.evaluations) || data.evaluations.length !== plans.length) fail('上月行动复盘不完整');
  const seen = new Set();
  for (const x of data.evaluations) {
    if (!object(x,['action_id','actual_value','score','status','evidence']) || !plans.some(p => p.action_id === x.action_id) || seen.has(x.action_id) || !string(x.evidence,200)) fail('复盘 ID 或证据异常');
    seen.add(x.action_id);
    if (!['达成','部分达成','未达成','信息不足'].includes(x.status)) fail('复盘状态异常');
    if (x.status === '信息不足' ? x.actual_value !== null || x.score !== null : !finite(x.actual_value) || !finite(x.score) || x.score < 0 || x.score > 100) fail('复盘数值异常');
    const p = plans.find(p => p.action_id === x.action_id);
    const actual = metricValue(p.metric,p.unit);
    if (x.actual_value !== null && actual !== undefined && Math.abs(actual-x.actual_value)>1e-8) fail('复盘实值与账本不符');
    if (x.score !== null) {
      const met = p.operator === '<=' ? x.actual_value <= Number(p.target_value) : p.operator === '>=' ? x.actual_value >= Number(p.target_value) : p.operator === '=' ? x.actual_value === Number(p.target_value) : null;
      if (met !== null && ((met && (x.status !== '达成' || x.score !== 100)) || (!met && (x.status === '达成' || x.score === 100)))) fail('复盘状态与目标矛盾');
    }
  }
  if (!Array.isArray(data.new_actions) || data.new_actions.length !== 5) fail('需要5条下月行动');
  let totalWeight = 0;
  const titles = new Set();
  for (const x of data.new_actions) {
    if (!object(x,['title','metric','category','operator','baseline_value','target_value','unit','weight','reason']) || !string(x.title,40) || !string(x.metric,80) || !string(x.reason,60) || titles.has(x.title)) fail('行动内容异常');
    titles.add(x.title);
    if (!['immediate','long_term'].includes(x.category) || !['<=','>=','='].includes(x.operator) || (!retained && ![...currencies,'次'].includes(x.unit)) || ![x.baseline_value,x.target_value,x.weight].every(finite) || x.baseline_value < 0 || x.target_value < 0 || x.weight <= 0 || x.weight > 100) fail('行动指标异常');
    const baseline = metricValue(x.metric,x.unit);
    if (!retained && (!Number.isFinite(baseline) || Math.abs(baseline-x.baseline_value)>1e-8)) fail('行动基线与账本不符');
    if (x.unit === '次' && (!Number.isInteger(x.baseline_value) || !Number.isInteger(x.target_value))) fail('次数必须为整数');
    totalWeight += x.weight;
  }
  if (Math.abs(totalWeight - 100) > 1e-8 || data.new_actions.filter(x => x.category === 'immediate').length !== 3) fail('行动权重或分类异常');

  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  // Ledger amounts remain decimal strings. BigInt avoids binary floating rounding.
  const decimal = value => {
    if (value && typeof value === 'object' && typeof value.n === 'bigint') return value;
    const match = String(value ?? '0').match(/^(-?)(\d+)(?:\.(\d+))?$/);
    if (!match) fail('账本金額不是有限十进制数');
    return {n: BigInt((match[1] || '') + match[2] + (match[3] || '')), scale: (match[3] || '').length};
  };
  const sub = (a,b) => { const x=decimal(a),y=decimal(b),s=Math.max(x.scale,y.scale);return {n:x.n*10n**BigInt(s-x.scale)-y.n*10n**BigInt(s-y.scale),scale:s}; };
  const divide = (value, divisor) => {const x=decimal(value),d=BigInt(divisor)*10n**BigInt(x.scale);return {n:(x.n*1000000n)/d,scale:6};};
  const money = value => {
    const x=typeof value==='object'?value:decimal(value), sign=x.n<0n?'-':'', n=x.n<0n?-x.n:x.n;
    const cents=x.scale>2?(n+5n*10n**BigInt(x.scale-3))/10n**BigInt(x.scale-2):n*10n**BigInt(2-x.scale);
    return sign+(cents/100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g,',')+'.'+(cents%100n).toString().padStart(2,'0');
  };
  const number = value => { const x=Number(value); if (!Number.isFinite(x)) fail('账本数值溢出'); return x; };
  const pct = (a,b) => number(b)>0 ? (number(a)/number(b)*100).toFixed(1)+'%' : '不适用';
  const scalar = x => typeof x==='object' ? Number(x.n)/10**x.scale : number(x);
  const total = (f,type,c) => f.totals[type].net[c] || '0';
  const names = {Food:'餐饮',Dining:'餐饮',Rent:'房租',Housing:'住房',Shopping:'购物',Transport:'交通',Transportation:'交通',Salary:'工资',Income:'收入',Expenses:'支出',Medical:'医疗',Health:'健康',Entertainment:'娱乐',Education:'教育',Utilities:'水电杂费',Subscriptions:'订阅',Travel:'旅行'};
  const account = a => a.replace(/^(?:Expenses|Income):/,'').split(':').map(x=>names[x]||x).join(' / ');
  const metricLabel = metric => { const parts=metric.split(' / '); return account(parts[0])+' · '+parts.slice(1).join(' / '); };
  const amount = (n,c) => `${money(n)} ${c}`;
  const text = [];
  let body = '';
  const block = (html,plain) => { body+=html; if (plain) text.push(plain); };
  const section = (title,html,plain) => {
    const key=['收支概览','较上月变化','较上月同期','支出明细','重点交易','值得关注','支出质量与习惯','上月行动复盘','数据口径'].find(x=>title.startsWith(x));
    const icon=({'收支概览':'◫','较上月变化':'↗','较上月同期':'↗','支出明细':'▦','重点交易':'≡','值得关注':'✦','支出质量与习惯':'◎','上月行动复盘':'✓','数据口径':'i'})[key] || '→';
    block(`<h2 style="margin:30px 0 14px;padding-top:20px;border-top:1px solid #e9e7e2;font-size:18px;line-height:1.5;font-weight:650;color:#37352f"><span style="display:inline-block;margin-right:9px;padding:2px 7px;background:#f0efeb;border-radius:5px;font-size:15px;color:#78746b">${icon}</span>${esc(title)}</h2>${html}`,`${title}\n${plain}`);
  };
  const p = html => `<p style="margin:0 0 10px;line-height:1.75">${html}</p>`;
  const muted = s => `<span style="color:#78746c;font-size:13px">${esc(s)}</span>`;
  const badge = (label, tone='gray') => {
    const [background,color]=({gray:['#efeeeb','#6d6a63'],blue:['#e8eef5','#456582'],green:['#e8f0e9','#477255'],amber:['#f5ecdc','#94703f']})[tone];
    return `<span style="display:inline-block;padding:2px 7px;border-radius:4px;background:${background};color:${color};font-size:12px;line-height:1.5;font-weight:500">${esc(label)}</span>`;
  };
  const row = (label,value,detail='',bar=null) => {
    const progress=bar===null?'':`<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;table-layout:fixed;margin-top:7px;background:#eeece7;border-radius:3px"><tr><td width="${Math.max(0,Math.min(100,bar)).toFixed(1)}%" style="height:4px;background:#a5b3a2;border-radius:3px;font-size:0;line-height:0"></td><td style="height:4px;font-size:0;line-height:0"></td></tr></table>`;
    return `<tr><td style="padding:12px 10px;border-bottom:1px solid #eeece7;width:52%;vertical-align:top">${esc(label)}${detail?'<br>'+muted(detail):''}${progress}</td><td style="padding:12px 10px;border-bottom:1px solid #eeece7;vertical-align:top;text-align:right;font-weight:600;font-variant-numeric:tabular-nums;color:#45433c">${esc(value)}</td></tr>`;
  };
  const table = rows => `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;table-layout:fixed;border-collapse:collapse;background:#fbfaf8;border:1px solid #eeece7">${rows}</table>`;
  const metrics = (entries,positive) => {
    const cells=entries.map(([label,value],index)=>{
      const [background,color]=index===2?(positive?['#eaf1e9','#42674b']:['#f7eae5','#995d4b']):index===3?['#ecf0f4','#4b627c']:['#f5f4f0','#37352f'];
      return `<td width="50%" style="width:50%;padding:5px;vertical-align:top"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;table-layout:fixed;background:${background};border-radius:7px"><tr><td class="metric" style="padding:15px 14px;word-break:break-word"><p style="margin:0 0 7px;font-size:12px;color:#78746c">${esc(label)}</p><p class="metric-value" style="margin:0;font-size:21px;line-height:1.45;font-weight:650;letter-spacing:-0.4px;color:${color};font-variant-numeric:tabular-nums">${esc(value)}</p></td></tr></table></td>`;
    });
    return `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;table-layout:fixed"><tr>${cells.slice(0,2).join('')}</tr><tr>${cells.slice(2,4).join('')}</tr><tr>${cells.slice(4,6).join('')}</tr></table>`;
  };
  const month = context.analysisMonth;
  const partial = context.reportMode === 'partial', historical = context.reportMode === 'history';
  const reportTitle = partial ? '本月财务进度' : revision ? '月度财务报告 · 修订版' : '月度财务报告';
  const modeNote = partial ? `截至 ${context.asOf}，本月尚未结束；仅统计已发生交易，计划目标用于本月剩余时间。` : historical ? '历史回顾：行动建议根据当月记录重建，不代表当时已有计划或已经执行。' : revision ? `修订 ${context.revision}：补账后的核算结果已更新。原行动目标与制定时基线保留，复盘按最新数据重算。` : '';
  if ((partial || historical) && !/^\d{4}-\d{2}-\d{2}$/.test(context.asOf || '')) fail('补发日期异常');
  block(`<p style="margin:0 0 10px;color:#9b978f;font-size:12px">个人财务 &nbsp; / &nbsp; 月度复盘</p><h1 style="margin:0 0 8px;font-size:30px;line-height:1.4;letter-spacing:-0.6px;font-weight:700;color:#37352f">${reportTitle}</h1><p style="margin:0 0 22px;font-size:13px;color:#89857d">${esc(month)} &nbsp; · &nbsp; ${facts.period.days_inclusive} 天 &nbsp; · &nbsp; ${facts.statistics.transaction_count} 笔记录</p><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;table-layout:fixed;background:#f5f0e6;border:1px solid #eae2d2;border-radius:7px"><tr><td style="width:32px;padding:16px 0 16px 14px;vertical-align:top;font-size:20px;color:#9b7c49">✦</td><td style="padding:16px 16px 16px 9px"><p style="margin:0 0 6px;font-size:12px;font-weight:600;color:#9b7c49">本月摘要</p><p style="margin:0;font-size:15px;line-height:1.75;font-weight:500;color:#514a3b">${esc(data.summary)}</p></td></tr></table>`,`${month} ${reportTitle}\n${data.summary}`);
  if (modeNote) block(`<p style="margin:12px 0 0;padding:10px 13px;background:#f2f4f6;border-radius:5px;font-size:13px;color:#6e7884">${esc(modeNote)}</p>`,modeNote);
  for (const c of currencies) {
    const income=total(facts,'income',c),expense=total(facts,'expenses',c),balance=sub(income,expense), i=number(income),e=number(expense),b=scalar(balance);
    const entries=[['净收入',amount(income,c)],['净支出',amount(expense,c)],['收支结余',amount(balance,c)],['结余率',i>0?(b/i*100).toFixed(1)+'%':'不适用'],['日均净支出',amount(divide(expense,facts.period.days_inclusive),c)],['收入 / 支出',i>=0&&e>0?(i/e).toFixed(2):'不适用']];
    section(`收支概览${currencies.length>1?' · '+c:''}`,metrics(entries,b>=0),entries.map(x=>x.join('：')).join('\n'));
    if (previous && previous.period.start.slice(0,7) === context.previousMonth) {
      const oldI=total(previous,'income',c),oldE=total(previous,'expenses',c),oldB=sub(oldI,oldE);
      const differences=[['净收入',income,oldI],['净支出',expense,oldE],['收支结余',balance,oldB]];
      const formatted=differences.map(([name,now,before])=>{
        const exact=sub(now,before),d=scalar(exact), rate=scalar(before)>0?(d/scalar(before)*100).toFixed(1)+'%':'增长率不适用';
        return [name,`${d>0?'+':''}${money(exact)} ${c}`,`上月 ${money(before)}；${rate}`];
      });
      const beforeRate=number(oldI)>0?scalar(oldB)/number(oldI)*100:null;
      formatted.push(['结余率',i>0&&beforeRate!==null?`${(b/i*100-beforeRate).toFixed(1)} 个百分点`:'不可比','与 '+context.previousMonth+(partial?' 同期比较':' 比较')]);
      section(`${partial?'较上月同期':'较上月变化'}${currencies.length>1?' · '+c:''}`,table(formatted.map(x=>row(...x)).join('')),formatted.map(x=>`${x[0]}：${x[1]}（${x[2]}）`).join('\n'));
    } else section('较上月变化',p(muted('上月缺少交易记录，暂不做环比。')), '上月缺少交易记录，暂不做环比。');
    const categories=Object.entries(facts.expenses_by_account).filter(([,v])=>Object.hasOwn(v,c)).sort((a,b)=>number(b[1][c])-number(a[1][c]));
    const refunds=number(facts.totals.expenses.refunds[c]||0), hasNegative=categories.some(([,v])=>number(v[c])<0);
    const catRows=categories.map(([a,v])=>[account(a),amount(v[c],c),e>0&&!hasNegative?pct(v[c],expense):'占比不适用']);
    const top3=categories.slice(0,3).reduce((sum,[,v])=>sum+number(v[c]),0);
    const note=[e>0&&!hasNegative?`前三项占净支出 ${pct(top3,expense)}。`:'存在净退款或没有正净支出，不计算分类占比。',refunds>0?`退款抵减 ${amount(facts.totals.expenses.refunds[c],c)}；支出按净额展示。`:''].filter(Boolean).join(' ');
    section(`支出明细${currencies.length>1?' · '+c:''}`,table(catRows.map((x,index)=>row(...x,e>0&&!hasNegative?number(categories[index][1][c])/e*100:null)).join(''))+`<p style="margin:10px 0 0">${muted(note)}</p>`,catRows.map(x=>`${x[0]}：${x[1]} · ${x[2]}`).join('\n')+'\n'+note);
    const large=(facts.top_expenses?.[c]||[]).map(x=>[`${x.date.slice(5)} · ${x.payee || x.narration || '未注明商户'}`,amount(x.amount,c),x.recognition==='accrual'?'权责确认，非当月现金支付':(x.payee&&x.narration?x.narration:'')]);
    const frequent=(facts.frequent_payees?.[c]||[]).map(x=>`${x.payee} ${x.count} 次，共 ${amount(x.amount,c)}`).join('；');
    section(`重点交易${currencies.length>1?' · '+c:''}`,table(large.map(x=>row(...x)).join(''))+p(muted(frequent?'高频商户：'+frequent:'没有重复商户记录。')),large.map(x=>`${x[0]}：${x[1]}${x[2]?' · '+x[2]:''}`).join('\n')+'\n'+(frequent?'高频商户：'+frequent:'没有重复商户记录。'));
  }
  const cards = xs => xs.map(x=>`<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;table-layout:fixed;margin-bottom:10px;background:#f1f3f5;border-left:3px solid #a7b4bf;border-radius:4px"><tr><td style="padding:15px 17px"><p style="margin:0 0 6px;font-size:15px;font-weight:600;color:#434c56">${esc(x.title)}</p><p style="margin:0 0 8px;line-height:1.7">${esc(x.detail)}</p>${muted('依据：'+x.evidence)}</td></tr></table>`).join('');
  const plainCards=xs=>xs.map(x=>`${x.title}：${x.detail}\n依据：${x.evidence}`).join('\n');
  if(data.insights.length) section('值得关注',cards(data.insights),plainCards(data.insights));
  if(data.observations.length) section('支出质量与习惯',cards(data.observations),plainCards(data.observations));
  let review = '',reviewText=[];
  let scoredWeight=0,weighted=0,allWeight=0;
  for (const plan of plans) {
    const x=data.evaluations.find(v=>v.action_id===plan.action_id), weight=Number(plan.weight);
    if(!Number.isFinite(weight)||weight<=0) fail('原行动权重异常');
    allWeight+=weight;
    if(x.score!==null){scoredWeight+=weight;weighted+=weight*x.score;}
    const detail=`目标 ${plan.operator} ${plan.target_value} ${plan.unit} · 实际 ${x.actual_value===null?'未知':x.actual_value+' '+plan.unit} · ${x.score===null?'未评分':x.score+' 分'}`;
    review+=p(`<strong>${esc(plan.title)}</strong> &nbsp; ${badge(x.status,x.status==='达成'?'green':x.status==='信息不足'?'gray':'amber')}<br>${muted(detail)}<br>${esc(x.evidence)}`);
    reviewText.push(`${plan.title} · ${x.status}\n${detail}\n${x.evidence}`);
  }
  const scoreNote=plans.length?(scoredWeight?`已评估部分 ${(weighted/scoredWeight).toFixed(0)} 分；权重覆盖 ${(scoredWeight/allWeight*100).toFixed(0)}%。资料不足项不计零分。`:'资料不足，暂不计算总分。'):'首期暂无上月行动，后续报告将逐条复盘。';
  section(partial?'本月行动进度（尚未结算）':'上月行动复盘',`<div style="padding:12px 14px;margin-bottom:14px;background:#f4f3ef;border-radius:5px">${muted(scoreNote)}</div>`+review,scoreNote+'\n'+reviewText.join('\n'));
  const nextMonth=new Date(Date.UTC(Number(month.slice(0,4)),Number(month.slice(5)),1)).toISOString().slice(0,7);
  const actions=data.new_actions.map((x,i)=>{
    const line=`${metricLabel(x.metric)} · ${x.operator} ${x.target_value} ${x.unit}（${retained?'制定时基线':'本月'} ${x.baseline_value} ${x.unit}；权重 ${x.weight}%）`;
    return {html:`<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;table-layout:fixed;margin-bottom:10px;border:1px solid #e9e6df;background:#fdfcf9;border-radius:6px"><tr><td style="width:30px;padding:15px 0 15px 13px;vertical-align:top"><span style="display:inline-block;width:26px;line-height:26px;text-align:center;border-radius:5px;background:#eeece5;color:#797363;font-size:13px;font-weight:600">${i+1}</span></td><td style="padding:15px 14px 15px 10px"><p style="margin:0 0 8px;font-weight:600">${esc(x.title)} &nbsp; ${badge(x.category==='immediate'?'立即执行':'长期习惯',x.category==='immediate'?'blue':'gray')}</p><p style="margin:0 0 6px;font-size:13px;color:#5d594f;line-height:1.7">${esc(line)}</p>${muted(x.reason)}</td></tr></table>`,plain:`${i+1}. ${x.title}（${x.category==='immediate'?'立即执行':'长期习惯'}）\n${line}\n${x.reason}`};
  });
  section(partial?'本月剩余时间行动':historical?`${nextMonth} 回顾建议`:`${nextMonth} ${retained?'原定行动计划':'行动计划'}`,actions.map(x=>x.html).join(''),actions.map(x=>x.plain).join('\n'));
  const limits=[`本月账本记录 ${facts.statistics.transaction_count} 笔。`, '范围：已入账交易；内部转账与信用卡还款不计入收支，退款已抵减。结余是账本收入与支出之差，并非现金流或净资产。', '未提供预算、完整资产负债与储备资料，暂不评价偿付能力或预测财富。',currencies.length>1?'多币种分别列示，未换算或合计。':'',...(facts.warnings||[]).map(String)].filter(Boolean);
  section('数据口径',`<div style="padding:15px 17px;background:#f4f3ef;border-radius:6px;line-height:1.8">${muted(limits.join(' '))}</div>`,limits.join('\n'));
  const html=`<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${esc(month)} ${reportTitle}</title><style>@media(max-width:480px){.page{padding:24px 16px!important}h1{font-size:27px!important}h2{font-size:17px!important}.metric{padding:13px 10px!important}.metric-value{font-size:18px!important}.cover{padding:17px 21px!important}}body,table,td,p{overflow-wrap:anywhere;word-wrap:break-word}a{color:#456582}</style></head><body style="margin:0;padding:0;background:#f3f2ee;color:#37352f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',Arial,sans-serif;font-size:15px;line-height:1.75;word-wrap:break-word;overflow-wrap:anywhere"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;table-layout:fixed"><tr><td align="center" style="padding:18px 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;max-width:720px;table-layout:fixed;background:#ffffff;border:1px solid #e7e4dc;border-radius:10px"><tr><td class="cover" style="padding:20px 32px;background:#ebe7dd;border-radius:10px 10px 0 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;table-layout:fixed"><tr><td style="width:60%;color:#807765;font-size:13px;font-weight:600;letter-spacing:1px">◫ &nbsp; 财务手记</td><td style="text-align:right">${badge(month,'gray')} ${historical||partial?badge(partial?'月中进度':'历史补发','blue'):''}</td></tr></table></td></tr><tr><td class="page" style="padding:30px 32px;word-break:break-word;word-wrap:break-word;overflow-wrap:anywhere">${body}<p style="margin:28px 0 0;border-top:1px solid #e9e7e2;padding-top:14px;color:#9a968d;font-size:12px">${esc(month)} &nbsp; · &nbsp; ${reportTitle}</p></td></tr></table></td></tr></table></body></html>`;
  if (Buffer.byteLength(html,'utf8') > 90000) fail('邮件超过安全展示长度');
  return {email_html:html,email_text:text.join('\n\n'),analysisMonth:month,previousActions:plans,new_actions:data.new_actions,evaluations:data.evaluations,template_version:2};
}
if (typeof module !== 'undefined') module.exports = report;
