/* Self-contained stored-observation chart. No fetch, external library or interpolation. */
(function(){
  document.querySelectorAll('table.metals').forEach(function(table){
    var rows=Array.from(table.querySelectorAll(':scope > tbody > .history-row'));
    if(!rows.length)return;
    var host=document.createElement('table');host.className='history-host';
    host.setAttribute('aria-label','선택한 금속 가격 이력');
    var body=document.createElement('tbody');host.appendChild(body);
    rows.forEach(function(row){body.appendChild(row);});
    table.parentElement.insertAdjacentElement('afterend',host);
  });
})();
(function(){
  'use strict';
  function format(value,unit){
    if(value===null || !Number.isFinite(value))return '—';
    if(unit.indexOf('%')>=0)return value.toLocaleString('ko-KR',{minimumFractionDigits:1,maximumFractionDigits:1})+unit;
    return value.toLocaleString('ko-KR',{maximumFractionDigits:2})+' '+unit;
  }
  function initialize(row){
    var data=JSON.parse(row.dataset.history),all=data.points,points=[],index=0;
    var svg=row.querySelector('svg'),path=svg.querySelector('path'),cursor=svg.querySelector('.history-cursor'),dot=svg.querySelector('circle');
    var observations=document.createElementNS('http://www.w3.org/2000/svg','g');observations.setAttribute('class','history-observations');svg.insertBefore(observations,path);
    var readout=row.querySelector('.history-readout'),body=row.querySelector('tbody'),period=row.querySelector('.history-period');
    var first=0,last=1,low=0,high=1;
    function stamp(point){return Date.parse(point.date+'T00:00:00Z');}
    function x(point){return first===last?458:48+(stamp(point)-first)/(last-first)*820;}
    function y(point){return 224-(point.value-low)/(high-low||1)*204;}
    function select(i){
      index=Math.max(0,Math.min(points.length-1,i));var p=points[index];
      if(!p){readout.textContent='저장된 가격 이력 없음';dot.setAttribute('visibility','hidden');return;}
      readout.textContent=p.date+'  '+format(p.value,data.unit);
      cursor.setAttribute('x1',x(p));cursor.setAttribute('x2',x(p));
      dot.setAttribute('visibility',p.value===null?'hidden':'visible');
      if(p.value!==null){dot.setAttribute('cx',x(p));dot.setAttribute('cy',y(p));}
    }
    function render(months){
      var cutoff='';
      if(months && all.length){
        var end=new Date(stamp(all[all.length-1])),m=end.getUTCMonth()-months,y0=end.getUTCFullYear();
        var target=new Date(Date.UTC(y0,m,1)),days=new Date(Date.UTC(target.getUTCFullYear(),target.getUTCMonth()+1,0)).getUTCDate();
        target.setUTCDate(Math.min(end.getUTCDate(),days));cutoff=target.toISOString().slice(0,10);
      }
      points=all.filter(function(p){return !cutoff || p.date>=cutoff;});
      var valid=points.filter(function(p){return p.value!==null && Number.isFinite(p.value);});
      first=points.length?stamp(points[0]):0;last=points.length?stamp(points[points.length-1]):1;
      low=valid.length?Math.min.apply(null,valid.map(function(p){return p.value;})):0;
      high=valid.length?Math.max.apply(null,valid.map(function(p){return p.value;})):1;
      if(high===low){high+=Math.abs(low)*.01||1;low-=Math.abs(low)*.01||1;}
      var connected=false,segments=[];
      points.forEach(function(p){if(p.value===null){connected=false;return;}segments.push((connected?'L':'M')+x(p).toFixed(2)+','+y(p).toFixed(2));connected=true;});
      path.setAttribute('d',segments.join(' '));body.replaceChildren();
      observations.replaceChildren();
      points.forEach(function(p,i){
        if(p.value!==null && (!points[i-1]||points[i-1].value===null) && (!points[i+1]||points[i+1].value===null)){
          var mark=document.createElementNS('http://www.w3.org/2000/svg','circle');mark.setAttribute('r','3');mark.setAttribute('cx',x(p));mark.setAttribute('cy',y(p));observations.append(mark);
        }
      });
      points.slice().reverse().forEach(function(p){var tr=document.createElement('tr'),date=document.createElement('td'),value=document.createElement('td');date.textContent=p.date;value.textContent=format(p.value,data.unit);tr.append(date,value);body.append(tr);});
      period.textContent=points.length?points[0].date+' ~ '+points[points.length-1].date+' · '+valid.length+'개 관측':'저장 이력 없음';
      row.querySelectorAll('.history-range').forEach(function(b){b.setAttribute('aria-pressed',String(Number(b.dataset.months)===months));});
      select(points.length-1);
    }
    row.querySelectorAll('.history-range').forEach(function(b){b.addEventListener('click',function(){render(Number(b.dataset.months));});});
    svg.addEventListener('pointermove',function(event){
      if(!points.length)return;
      var box=svg.getBoundingClientRect(),position=(event.clientX-box.left)/box.width*900;
      var target=first+(position-48)/820*(last-first),lo=0,hi=points.length-1;
      while(lo<hi){var mid=Math.floor((lo+hi)/2);if(stamp(points[mid])<target)lo=mid+1;else hi=mid;}
      if(lo && Math.abs(stamp(points[lo-1])-target)<Math.abs(stamp(points[lo])-target))lo--;
      select(lo);
    });
    svg.addEventListener('keydown',function(event){if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();select(index+(event.key==='ArrowLeft'?-1:1));}});
    render(0);
  }
  document.querySelectorAll('.history-toggle').forEach(function(button){
    button.addEventListener('click',function(){var row=document.getElementById(button.getAttribute('aria-controls'));var open=row.hidden;row.hidden=!open;button.setAttribute('aria-expanded',String(open));if(open && !row.dataset.ready){initialize(row);row.dataset.ready='true';}});
  });
})();
