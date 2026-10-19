"""Sparse numeric COM writes grouped into adjacent rectangles, never across gaps."""
from decimal import Decimal,InvalidOperation

def contiguous_blocks(edits):
    rows={}
    for e in edits:
        key=(int(e['row']),int(e['col']))
        if key in rows:raise ValueError('동일 셀 중복 변경')
        rows[key]=e['incoming']
    byrow={}
    for (r,c),v in sorted(rows.items()):byrow.setdefault(r,[]).append((c,v))
    blocks=[];last={}
    for r,cells in byrow.items():
        spans=[]
        for c,v in cells:
            if spans and c==spans[-1][0]+len(spans[-1][1]):spans[-1][1].append(v)
            else:spans.append([c,[v]])
        current={}
        for c,values in spans:
            key=(c,len(values));prior=last.get(key)
            if prior is not None and prior['row']+prior['height']==r:
                prior['values'].append(tuple(values));prior['height']+=1;block=prior
            else:
                block={'row':r,'col':c,'height':1,'width':len(values),'values':[tuple(values)]};blocks.append(block)
            current[key]=block
        last=current
    return blocks

def block_range(ws,b):return ws.Range(ws.Cells(b['row'],b['col']),ws.Cells(b['row']+b['height']-1,b['col']+b['width']-1))

def put_blocks(ws,edits,history=None):
    blocks=contiguous_blocks(edits)
    for b in blocks:
        target=block_range(ws,b)
        if history is not None:history.append((target,target.Value2))
        target.Value2=tuple(b['values'])
    return len(blocks)
