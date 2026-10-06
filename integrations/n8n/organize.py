"""Canvas layout helpers for the single workflow generator."""
from collections import defaultdict, deque
from copy import deepcopy
import uuid

def edges(workflow, main_only=False):
    for source, kinds in workflow['connections'].items():
        for kind, branches in kinds.items():
            if main_only and kind != 'main':
                continue
            for index, branch in enumerate(branches):
                for edge in branch:
                    yield source, edge['node'], kind, index

def ranks(names, connections):
    incoming = defaultdict(int)
    children = defaultdict(list)
    for source, target, *_ in connections:
        if source in names and target in names:
            children[source].append(target)
            incoming[target] += 1
    queue = deque(n for n in names if not incoming[n])
    rank = {n: 0 for n in names}
    count = 0
    while queue:
        source = queue.popleft()
        count += 1
        for target in children[source]:
            rank[target] = max(rank[target], rank[source] + 1)
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    if count != len(names):
        raise ValueError('Workflow contains a cycle; needs a separate canvas plan')
    return rank

def note(workflow, title, description, members, color=7):
    xs, ys = zip(*(node['position'] for node in members))
    return {'id': str(uuid.uuid5(uuid.NAMESPACE_URL, workflow['id'] + '/layout/' + title)),
            'name': '布局 · ' + title, 'type': 'n8n-nodes-base.stickyNote', 'typeVersion': 1,
            'position': [min(xs)-65, min(ys)-155],
            'parameters': {'content': f'## {title}\n{description}', 'color': color,
                           'width': max(xs)-min(xs)+270, 'height': max(ys)-min(ys)+340}}

def arrange(workflow):
    result = deepcopy(workflow)
    # Replace tutorial decoration with concise stage explanations; originals stay
    # in the private backup. All executable nodes and parameters remain intact.
    result['nodes'] = [n for n in result['nodes'] if not n['type'].endswith('.stickyNote')]
    nodes = {n['name']: n for n in result['nodes']}
    connections = list(edges(result))
    main = [e for e in connections if e[2] == 'main']
    helpers = {a for a,b,kind,_ in connections if kind.startswith('ai_') and not any(a in e[:2] for e in main)}
    errors = {n for n in nodes if n in ('下载失败','账单处理失败','月报执行失败')}
    for source,target,kind,index in main:
        if index == 1 and nodes[source].get('onError') == 'continueErrorOutput':
            errors.add(target)
    changed = True
    while changed:
        changed = False
        for source,target,*_ in main:
            if source in errors and target not in errors:
                errors.add(target)
                changed = True
    normal = [n for n in nodes if n not in helpers | errors]
    rank = ranks(normal, main)
    desired = {n: 0 for n in normal}
    for name in sorted(normal, key=lambda n:rank[n]):
        parents = [(a,index) for a,b,_,index in main if b == name and a in rank]
        if parents:
            desired[name] = sum(desired[a] + (280 if index == 1 else 0) for a,index in parents)/len(parents)
    by_rank = defaultdict(list)
    for name in normal:
        by_rank[rank[name]].append(name)
    for level, names in by_rank.items():
        names.sort(key=lambda n:(desired[n], nodes[n]['position'][1], n))
        previous = -10000
        for name in names:
            y = max(desired[name], previous+260)
            nodes[name]['position'] = [level*320, int(y)]
            previous = y
    name = workflow['name']
    # Place bypass paths away from the nodes they skip, so wires stay readable.
    overrides = {
        '财务月报': {'写回上月评分':260},
        '账单入账': {'AI Agent':-440, '校验分类决策':-440},
        '账单文件': {'下载微信账单':280},
        '屏幕时间周报': {'仅返回重复请求':520,'返回重复结果':520,'静默处理':360},
        '生活助手': {'Get Voice File':-320,'Transcribe a recording':-320},
    }
    if name in ('财务月报','账单入账','账单文件','屏幕时间周报','生活助手'):
        for n in normal:
            nodes[n]['position'][1] = 0
    for n,y in overrides.get(name,{}).items():
        if n in nodes:
            nodes[n]['position'][1] = y
    if name == '月报调度':
        nodes['Schedule Trigger']['position'][1] = -160
        nodes['Bill 仓库同步完成']['position'][1] = 160
    helper_targets = defaultdict(list)
    for source,target,kind,_ in connections:
        if source in helpers:
            helper_targets[target].append(source)
    for target,sources in helper_targets.items():
        sources.sort(key=lambda n:nodes[n]['type'])
        for index,source in enumerate(sources):
            x,y = nodes[target]['position']
            nodes[source]['position'] = [int(x + (index-(len(sources)-1)/2)*240), y+240]
    if name == '账单入账' and 'Google Gemini Chat Model' in nodes:
        nodes['Google Gemini Chat Model']['position'][1] = -200
    if errors:
        error_rank = ranks(sorted(errors), main)
        start = max((rank[a] for a,b,_,_ in main if b in errors and a in rank),default=0)+1
        error_y = min((nodes[n]['position'][1] for n in nodes if n not in errors),default=0)-520
        for n in errors:
            nodes[n]['position'] = [(start+error_rank[n])*320, error_y]
    labels = {
        '财务月报': {'Code in JavaScript':'校验月份并准备请求','AI Agent':'生成结论与结构化行动','Send email':'HTML 与纯文本双格式'},
        '月报调度': {"Call 'Bill analyze'":'逐月生成财务月报','Schedule Trigger':'每天 00:10 检查'},
        '账单入账': {'BillFlow':'单封账单邮件输入','AI Agent':'仅处理待分类项目'},
        '账单问答': {'AI Agent':'调用账本查询工具'},
        '账本查询': {'When Executed by Another Workflow':'接收日期范围参数'},
    }
    for node in result['nodes']:
        if node['name'] in labels.get(name,{}) and not node.get('notes'):
            node['notes']=labels[name][node['name']]
            node['notesInFlow']=True
    # Notes enclose logical stages and stay behind the executable nodes.
    stage_specs = {
        '财务月报': [(0,4,'01 月份与账本','读取完整账本，检查月份并领取生成任务。'),(5,8,'02 分析与校验','结合真实上月计划、Fane 核算和简短分析。'),(9,11,'03 报告存档','校验账本快照，保存固定版式报告。'),(12,99,'04 行动与投递','保存计划和复盘，再发送一封邮件并登记成功。')],
        '账单入账': [(0,3,'01 准备账单','读取文件并检查入账准备结果。'),(4,6,'02 可选分类','有待分类项才调用模型；无待分类项直接继续。'),(7,99,'03 写入与提交','应用校验后的分类，生成订阅并提交账本。')],
        '账单文件': [(0,2,'01 邮件校验','识别来源，检查账单邮件与附件。'),(3,4,'02 文件获取','支付宝使用附件；微信下载账单。'),(5,99,'03 解密与准备','上传、解密、验证文件并准备入账。')],
        '账本同步': [(0,2,'01 接收与验签','验证 GitHub 原始请求，过滤事件与分支。'),(3,99,'02 回应与月报','回应同步结果，同步成功再检查月报。')],
        '屏幕时间周报': [(0,4,'01 数据与去重','检查请求质量并读取历史，重复周期直接返回。'),(5,9,'02 分析与存档','生成趋势和分析，保存周报记录。'),(10,99,'03 投递与状态','需要通知才发邮件，之后登记结果并回应。')],
    }
    if name in stage_specs:
        for low,high,title,description in stage_specs[name]:
            members=[nodes[n] for n in normal if low<=rank[n]<=high]
            group_names={n['name'] for n in members}
            members += [nodes[h] for target,hs in helper_targets.items() if target in group_names for h in hs]
            if members:
                result['nodes'].append(note(result,title,description,members))
    else:
        members=[nodes[n] for n in normal]+[nodes[h] for h in helpers]
        if members:
            result['nodes'].append(note(result,name,'主线从左到右；分支和模型独立排列。',members))
    if errors:
        result['nodes'].append(note(result,'异常出口','失败在此汇总，保留原处理行为。',[nodes[n] for n in errors],3))
    return result
