"""Monthly report eligibility and atomic generation records for n8n."""
import hashlib
import json
import re
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])\Z")
LEASE_SECONDS = 6 * 60 * 60
ROOT = Path.home() / '.flow'

def current_month():
    return datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m')


def previous_month(month):
    year, number = map(int, month.split('-'))
    return f'{year - (number == 1):04d}-{number - 1 if number > 1 else 12:02d}'


def validate_month(month):
    if not isinstance(month, str) or not MONTH.fullmatch(month):
        raise ValueError('Invalid analysis month')
    return month


class Reports:
    """Ledger observations, one delivery claim, and immutable sent revisions."""
    def __init__(self, root=ROOT, now=current_month, ledger=None, clock=time.time):
        self.root, self.now, self.clock = root, now, clock
        self.settings = json.loads((root / 'config/monthly-report.json').read_text())
        self.floor = validate_month(self.settings['start_month'])
        directory = root / 'state/monthly-reports'
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / 'reports.sqlite'
        self.db = sqlite3.connect(path, timeout=30)
        path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS reports(month TEXT PRIMARY KEY,status TEXT NOT NULL,
              token TEXT,claimed_at REAL,source_hash TEXT,generated_at TEXT,sent_at TEXT,report_json TEXT);
            CREATE TABLE IF NOT EXISTS observations(month TEXT PRIMARY KEY,input_hash TEXT,changed_at REAL);
            CREATE TABLE IF NOT EXISTS activity(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS jobs(month TEXT PRIMARY KEY,status TEXT,token TEXT,claimed_at REAL,
              source_hash TEXT,revision INTEGER,generated_at TEXT,sent_at TEXT,report_json TEXT);
            CREATE TABLE IF NOT EXISTS history(month TEXT,revision INTEGER,source_hash TEXT,
              sent_at TEXT,report_json TEXT,PRIMARY KEY(month,revision));
        ''')
        columns = {r['name'] for r in self.db.execute('PRAGMA table_info(reports)')}
        for name, kind in [('semantic_hash','TEXT'), ('revision','INTEGER DEFAULT 1')]:
            if name not in columns:
                self.db.execute(f'ALTER TABLE reports ADD COLUMN {name} {kind}')
        self.db.commit()
        self.ledger, self.facts, self.hashes = ledger, {}, {}

    def load(self):
        if self.ledger is None:
            from .snapshot import snapshot
            data = snapshot(self.root / 'data/account/main.bean')
            self.ledger, self.facts, self.hashes = data['ledger'], data['facts'], data['hashes']
        return self.ledger

    def source_hash(self, month):
        self.load()
        # The text fallback is for test fixtures. Production uses normalized postings.
        hashes = [self.hashes.get(m) or hashlib.sha256(self.ledger.get(m,'').encode()).hexdigest()
                  for m in (month, previous_month(month))]
        return hashlib.sha256(json.dumps(hashes).encode()).hexdigest()

    def bootstrap(self, hashes=None):
        """Adopt existing receipts once, without sending or changing old report bodies."""
        self.load()
        with self.db:
            for row in self.db.execute('SELECT * FROM reports WHERE semantic_hash IS NULL').fetchall():
                digest = self.source_hash(row['month']) if hashes is None else hashlib.sha256(json.dumps([
                    hashes.get(m) or hashlib.sha256(b'').hexdigest()
                    for m in (row['month'],previous_month(row['month']))]).encode()).hexdigest()
                self.db.execute('UPDATE reports SET semantic_hash=? WHERE month=?', (digest,row['month']))
                if row['status'] == 'sent':
                    self.db.execute('INSERT OR IGNORE INTO history VALUES(?,?,?,?,?)',
                                    (row['month'],row['revision'],digest,row['sent_at'],row['report_json']))
        return self.notice()

    def notice(self, dry_run=False):
        self.load()
        if dry_run:
            return {'observed':False,'dryRun':True}
        changes = 0
        with self.db:
            self.db.execute("INSERT INTO activity VALUES('updated_in',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(self.now(),))
            for month in self.ledger:
                if not self.floor <= month <= self.now():
                    continue
                digest = self.source_hash(month)
                cursor = self.db.execute('''INSERT INTO observations VALUES(?,?,?)
                  ON CONFLICT(month) DO UPDATE SET input_hash=excluded.input_hash,changed_at=excluded.changed_at
                  WHERE observations.input_hash!=excluded.input_hash''', (month,digest,self.clock()))
                changes += cursor.rowcount
        return {'observed':True,'changed_months':changes}

    def check(self, month):
        validate_month(month)
        if month >= self.now():
            return 'month-not-closed'
        if month < self.floor:
            return 'before-start-month'
        text = self.load().get(month, '')
        if not text:
            return 'no-transactions'
        source = self.root / f'data/account/journal/{month[:4]}/{month}.bean'
        raw = source.read_text() if source.is_file() else ''
        if re.search('fixme', text + '\n' + raw, re.I):
            return 'fixme'
        job = self.db.execute('SELECT * FROM jobs WHERE month=?',(month,)).fetchone()
        if job and job['status'] in ('generated','sending'):
            return 'delivery-pending'  # Never retry a possibly delivered email.
        if job and job['status']=='processing' and job['claimed_at'] > self.clock()-LEASE_SECONDS:
            return 'in-progress'
        row = self.db.execute('SELECT * FROM reports WHERE month=?',(month,)).fetchone()
        if row and (row['status']=='generated' or row['semantic_hash'] is None or
                    row['semantic_hash']==self.source_hash(month)):
            return 'already-generated'
        observed = self.db.execute('SELECT * FROM observations WHERE month=?',(month,)).fetchone()
        if not observed or observed['input_hash']!=self.source_hash(month):
            return 'awaiting-ledger-update'
        latest_change = self.db.execute('SELECT MAX(changed_at) FROM observations').fetchone()[0]
        if self.clock()-latest_change < self.settings.get('settle_seconds',600):
            return 'settling'
        if not row:
            year, number = map(int,month.split('-'))
            next_month = f'{year+(number==12):04d}-{number+1 if number<12 else 1:02d}'
            activity=self.db.execute("SELECT value FROM activity WHERE key='updated_in'").fetchone()
            if not activity or activity['value']<next_month:
                return 'awaiting-rollover'
        return None

    def plan(self, dry_run=False):
        return [{'analysisMonth':m,'dryRun':dry_run} for m in sorted(self.load())
                if self.floor<=m<self.now() and self.check(m) is None]

    def actions(self, month):
        path = self.root / 'state/n8n/database.sqlite'
        if not path.exists():
            return []
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute('SELECT * FROM data_table_user_eRhKVHIQoJ6SPCLw WHERE target_month=?',(month,))]

    def prepare(self, request):
        month = validate_month(request['analysisMonth'])
        self.load()
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            reason = self.check(month)
            if request.get('dryRun') is True:
                reason = reason or 'dry-run'
            if reason:
                return {'eligible':False,'analysisMonth':month,'reason':reason}
            previous = self.db.execute('SELECT * FROM reports WHERE month=?',(month,)).fetchone()
            revision = (previous['revision']+1) if previous else 1
            token, digest = str(uuid.uuid4()),self.source_hash(month)
            self.db.execute('''INSERT INTO jobs(month,status,token,claimed_at,source_hash,revision)
                VALUES(?,'processing',?,?,?,?) ON CONFLICT(month) DO UPDATE SET status='processing',
                token=excluded.token,claimed_at=excluded.claimed_at,source_hash=excluded.source_hash,
                revision=excluded.revision,report_json=NULL,generated_at=NULL,sent_at=NULL''',
                (month,token,self.clock(),digest,revision))
        before = previous_month(month)
        old = json.loads(previous['report_json']) if previous and previous['report_json'] else {}
        return {'eligible':True,'analysisMonth':month,'previousMonth':before,'claimToken':token,
                'sourceHash':digest,'revision':revision,
                'reportMode':'history' if previous and previous['token']=='backfill-20261006' else 'revision' if previous else 'normal',
                'asOf':datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(),
                'retainedActions':old.get('new_actions') if previous else None,
                'previousActions':self.actions(month),
                'ledgerData':f'CURRENT_MONTH {month}\n{self.ledger[month]}\nPREVIOUS_MONTH {before}\n{self.ledger.get(before,"(No transactions)")}',
                'facts':self.facts.get(month),'previousFacts':self.facts.get(before)}

    def store(self, request):
        month = validate_month(request['analysisMonth'])
        report = request['report']
        if report.get('analysisMonth')!=month or not report.get('email_html') or not report.get('email_text'):
            raise ValueError('Invalid report payload')
        source = self.root / f'data/account/journal/{month[:4]}/{month}.bean'
        if re.search('fixme',self.load().get(month,'')+'\n'+(source.read_text() if source.is_file() else ''),re.I):
            self.release(request)
            return {'stored':False,'reason':'fixme'}
        with self.db:
            cursor = self.db.execute('''UPDATE jobs SET status='generated',generated_at=?,report_json=?
              WHERE month=? AND status='processing' AND token=? AND source_hash=?''',
              (datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),json.dumps(report,ensure_ascii=False),
               month,request['claimToken'],self.source_hash(month)))
            if not cursor.rowcount:
                self.db.execute("DELETE FROM jobs WHERE month=? AND status='processing' AND token=?",(month,request['claimToken']))
                return {'stored':False,'reason':'claim-or-ledger-changed'}
        return {'stored':True,'analysisMonth':month,'claimToken':request['claimToken']}

    def begin(self, request):
        month = validate_month(request['analysisMonth'])
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute("SELECT * FROM jobs WHERE month=? AND status='generated' AND token=?",(month,request['claimToken'])).fetchone()
            if not row:
                raise ValueError('Delivery already started or receipt uncertain')
            if row['source_hash']!=self.source_hash(month):
                self.db.execute("DELETE FROM jobs WHERE month=? AND status='generated'",(month,))
                return {'eligible':False,'reason':'ledger-changed-before-send'}
            self.db.execute("UPDATE jobs SET status='sending' WHERE month=?",(month,))
        return {**json.loads(row['report_json']),'claimToken':row['token'],'revision':row['revision'],
                'mail_subject':f'{month} 财务月报'+(f' · 修订 {row["revision"]}' if row['revision']>1 else '')}

    def persist_actions(self, month, report, revision):
        path = self.root / 'state/n8n/database.sqlite'
        if not path.exists():
            return
        table = 'data_table_user_eRhKVHIQoJ6SPCLw'
        now = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
        year,number = map(int,month.split('-'))
        target = f'{year+(number==12):04d}-{number+1 if number<12 else 1:02d}'
        with sqlite3.connect(path,timeout=30) as db:
            if revision==1:
                for index,action in enumerate(report.get('new_actions',[]),1):
                    identifier=f'{target}-{index:02d}'
                    if db.execute(f'SELECT 1 FROM {table} WHERE action_id=?',(identifier,)).fetchone():
                        continue
                    fields=['title','metric','category','operator','baseline_value','target_value','unit','weight']
                    db.execute(f'INSERT INTO {table}(action_id,source_month,target_month,{",".join(fields)},status,evidence,created_at) VALUES({",".join("?" for _ in range(14))})',
                               [identifier,month,target]+[action[k] for k in fields]+['待评估','',now])
            for evaluation in report.get('evaluations',[]):
                db.execute(f'''UPDATE {table} SET actual_value=?,score=?,status=?,evidence=?,evaluated_at=?,
                    updatedAt=STRFTIME('%Y-%m-%d %H:%M:%f','NOW') WHERE action_id=? AND target_month=?''',
                           [evaluation[k] for k in ('actual_value','score','status','evidence')]+[now,evaluation['action_id'],month])

    def sent(self, request):
        month = validate_month(request['analysisMonth'])
        if not request.get('messageId') or request.get('accepted_count',0)<1 or request.get('rejected_count',0):
            raise ValueError('SMTP receipt not accepted')
        row = self.db.execute('SELECT * FROM jobs WHERE month=? AND token=?',(month,request['claimToken'])).fetchone()
        if not row or row['status'] not in ('sending','sent'):
            raise ValueError('Invalid delivery claim')
        report=json.loads(row['report_json'])
        self.persist_actions(month,report,row['revision'])
        now = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO history VALUES(?,?,?,?,?)',(month,row['revision'],row['source_hash'],now,row['report_json']))
            self.db.execute('''INSERT INTO reports(month,status,token,source_hash,semantic_hash,revision,generated_at,sent_at,report_json)
                VALUES(?,'sent',?,?,?,?,?,?,?) ON CONFLICT(month) DO UPDATE SET status='sent',token=excluded.token,
                source_hash=excluded.source_hash,semantic_hash=excluded.semantic_hash,revision=excluded.revision,
                generated_at=excluded.generated_at,sent_at=excluded.sent_at,report_json=excluded.report_json''',
                (month,row['token'],row['source_hash'],row['source_hash'],row['revision'],row['generated_at'],now,row['report_json']))
            self.db.execute("UPDATE jobs SET status='sent',sent_at=? WHERE month=?",(now,month))
        return {'sent':True,'analysisMonth':month,'revision':row['revision']}

    def release(self, request):
        with self.db:
            self.db.execute("DELETE FROM jobs WHERE month=? AND status='processing' AND token=?",(validate_month(request['analysisMonth']),request['claimToken']))
        return {'released':True}

