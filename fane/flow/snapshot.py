"""One validated ledger snapshot; used by reports and historical backfill."""

def snapshot(path, cutoff=None, day=None):
    import io,json,calendar,hashlib
    from datetime import date
    from fane.query.engine import query_entries,transaction_recognition
    from beancount import loader
    from beancount.core.data import Transaction
    from beancount.parser import printer
    entries,errors,_=loader.load_file(str(path))
    if errors:
        raise RuntimeError('Ledger validation failed; fix the ledger before reporting')
    months={}
    for entry in entries:
        if isinstance(entry,Transaction) and (cutoff is None or entry.date<=cutoff) and (day is None or entry.date.day<=day):
            months.setdefault(entry.date.strftime('%Y-%m'),[]).append(entry)
    result={}
    facts={}
    hashes={}
    def economic_units(unit):
        return [format(unit.number.normalize(),'f'),unit.currency] if unit else None
    def economic(entry):
        postings=[]
        for p in entry.postings:
            cost=p.cost
            postings.append([p.account,economic_units(p.units),economic_units(p.price),
                [format(cost.number.normalize(),'f'),cost.currency,str(cost.date)] if cost else None])
        return [str(entry.date),entry.payee,transaction_recognition(entry),sorted(postings,key=lambda p:json.dumps(p))]
    for month,items in months.items():
        output=io.StringIO()
        printer.print_entries(items,file=output)
        result[month]=output.getvalue()
        hashes[month]=hashlib.sha256(json.dumps(sorted((economic(e) for e in items),key=lambda e:json.dumps(e)),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        year,number=map(int,month.split('-'))
        query=query_entries(items,start_date=date(year,number,1),end_date=min(cutoff or date.max,date(year,number,min(day or 31,calendar.monthrange(year,number)[1]))),max_transactions=len(items))
        # Keep all aggregates, but only the five largest expenses and frequent payees.
        from decimal import Decimal
        expenses=[]
        frequencies={}
        counts={}
        for transaction in query.pop('transactions'):
            for account in set(p['account'] for p in transaction['postings'] if p['account_type'] in ('Income','Expenses')):
                counts[account]=counts.get(account,0)+1
            amounts={}
            for posting in transaction['postings']:
                if posting['account_type']=='Expenses' and posting['units']:
                    unit=posting['units']
                    amounts[unit['currency']]=amounts.get(unit['currency'],Decimal(0))+Decimal(unit['number'])
            for currency,amount in amounts.items():
                if amount>0:
                    expenses.append(dict(date=transaction['date'],payee=transaction['payee'],narration=transaction['narration'],currency=currency,amount=str(amount),recognition=transaction['recognition']))
                    payee=transaction['payee'] or '(未注明商户)'
                    key=(currency,payee)
                    count,total=frequencies.get(key,(0,Decimal(0)))
                    frequencies[key]=(count+1,total+amount)
        currencies=sorted(set(query['totals']['income']['net'])|set(query['totals']['expenses']['net']))
        query['top_expenses']={c:sorted((x for x in expenses if x['currency']==c),key=lambda x:Decimal(x['amount']),reverse=True)[:5] for c in currencies}
        query['frequent_payees']={c:[dict(payee=k[1],count=v[0],amount=str(v[1])) for k,v in sorted(frequencies.items(),key=lambda x:(x[1][0],x[1][1]),reverse=True) if k[0]==c and v[0]>1][:5] for c in currencies}
        query['account_counts']=counts
        facts[month]=query
    return dict(ledger=result,facts=facts,hashes=hashes)
