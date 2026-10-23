/* MIA offline market report: independent scale per instrument, no CDN/API calls. */
(() => {
  "use strict";
  const root = document.getElementById("market-data");
  if (!root) return;
  let snapshot;
  try { snapshot = JSON.parse(root.content.textContent.trim()); }
  catch (_) { return; }
  const ns = "http://www.w3.org/2000/svg";
  const fmt = n => new Intl.NumberFormat("ko-KR", {maximumFractionDigits:6}).format(n);
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const svgNode = (tag, attrs) => {
    const n = document.createElementNS(ns, tag);
    Object.entries(attrs || {}).forEach(([k,v]) => n.setAttribute(k, String(v)));
    return n;
  };
  const minusMonths = (date, months) => {
    const copy = new Date(date.getTime());
    copy.setUTCMonth(copy.getUTCMonth()-months);
    return copy.toISOString().slice(0,10);
  };
  function draw(panel, series, range, minMonth, maxMonth) {
    const chart = panel.querySelector(".trend-plot");
    const overlay = panel.querySelector(".trend-tooltip");
    const desc = panel.querySelector(".trend-value");
    chart.replaceChildren();
    overlay.hidden = true;
    const all = series.points || [];
    let cutoff = "";
    if (range !== "all" && all.length) {
      cutoff = minusMonths(new Date(all[all.length-1].date+"T12:00:00Z"), Number(range));
    }
    const points = all.filter(p => (!cutoff || p.date >= cutoff) &&
      (!minMonth || p.date.slice(0,7) >= minMonth) &&
      (!maxMonth || p.date.slice(0,7) <= maxMonth));
    const latest = points[points.length-1];
    desc.textContent = latest ?
      fmt(latest.value) + " " + (series.unit || "") + " · " + latest.date + " · " + series.source :
      "선택 기간에 검증된 관측값이 없습니다.";
    if (!points.length) {
      chart.append(svgNode("text", {x:450,y:145,"text-anchor":"middle",class:"trend-empty"}))
        .textContent = "선택한 기간에 저장된 자료가 없습니다";
      return;
    }
    const width=900,height=268,left=76,right=24,top=20,bottom=42;
    const vals=points.map(p => Number(p.value));
    let low=Math.min(...vals),high=Math.max(...vals);
    if (low===high) { const expand=Math.max(Math.abs(low)*.015,.001); low-=expand;high+=expand; }
    else { const pad=(high-low)*.12;low-=pad;high+=pad; }
    const X=i=>left+(width-left-right)*(points.length===1?.5:i/(points.length-1));
    const Y=v=>top+(height-top-bottom)*(1-(v-low)/(high-low));
    for(let i=0;i<=4;i++){
      const y=top+(height-top-bottom)*i/4;
      chart.append(svgNode("line",{x1:left,y1:y,x2:width-right,y2:y,class:"trend-grid"}));
      const l=svgNode("text",{x:left-10,y:y+4,"text-anchor":"end",class:"trend-tick"});
      l.textContent=fmt(high-(high-low)*i/4);chart.append(l);
    }
    const steps=Math.min(5,points.length);
    for(let i=0;i<steps;i++){
      const idx=steps===1?0:Math.round(i*(points.length-1)/(steps-1));
      const l=svgNode("text",{x:X(idx),y:height-12,"text-anchor":"middle",class:"trend-tick"});
      l.textContent=points[idx].date.slice(2);chart.append(l);
    }
    const line=svgNode("polyline",{points:points.map((p,i)=>X(i)+","+Y(p.value)).join(" "),
      class:"trend-line",fill:"none"});chart.append(line);
    const last=svgNode("circle",{cx:X(points.length-1),cy:Y(latest.value),r:4,class:"trend-dot"});
    chart.append(last);
    const cross=svgNode("line",{x1:0,x2:0,y1:top,y2:height-bottom,class:"trend-cross"});
    const dot=svgNode("circle",{cx:0,cy:0,r:5,class:"trend-focus"});
    cross.style.display=dot.style.display="none";
    chart.append(cross,dot);
    const move=e=>{
      const rect=chart.getBoundingClientRect();
      const x=(e.clientX-rect.left)*width/Math.max(rect.width,1);
      let idx=Math.round((x-left)/(width-left-right)*(points.length-1));
      idx=Math.max(0,Math.min(points.length-1,idx));
      const p=points[idx],xx=X(idx),yy=Y(p.value);
      cross.setAttribute("x1",xx);cross.setAttribute("x2",xx);
      dot.setAttribute("cx",xx);dot.setAttribute("cy",yy);
      cross.style.display=dot.style.display="";
      overlay.hidden=false;
      overlay.textContent=p.date+"  ·  "+fmt(p.value)+" "+(series.unit||"")+"  ·  "+series.source;
      overlay.style.left=Math.max(10,Math.min(68,xx/width*100))+"%";
    };
    chart.onpointermove=move;
    chart.onpointerleave=()=>{cross.style.display=dot.style.display="none";overlay.hidden=true;};
    chart.onfocus=()=>{if(latest)desc.textContent=fmt(latest.value)+" "+(series.unit||"")+" · "+latest.date;};
  }
  const groups = new Map((snapshot.groups||[]).map(g=>[g.id,g]));
  document.querySelectorAll(".market-group[data-group]").forEach(section=>{
    const group=groups.get(section.dataset.group);
    if (!group) return;
    const picker=section.querySelector(".trend-series");
    const plot=section.querySelector(".trend-chart");
    if (!picker||!plot) return;
    const rangeButtons=[...section.querySelectorAll("[data-range]")];
    const from=section.querySelector(".trend-from"),to=section.querySelector(".trend-to");
    const options=group.series||[];
    const available=options.filter(s=>s.points&&s.points.length);
    if (!options.length){
      picker.append(el("span","검증된 저장 시세 없음 · 추가 원천 연동 전","muted-inline"));
      plot.hidden=true;
      return;
    }
    let current=options.find(s=>s.points&&s.points.length) || options[0];
    let range="3";
    function redraw(){
      plot.hidden=false;
      rangeButtons.forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.range===range)));
      draw(section,current,range,from.value,to.value);
    }
    options.forEach(s=>{
      const button=el("button",s.name+" · "+s.source,"series-pill");
      button.type="button";
      button.title=s.code+" | "+s.unit+" | "+s.status;
      button.addEventListener("click",()=>{
        current=s;
        [...picker.querySelectorAll("button")].forEach(b=>b.setAttribute("aria-pressed",String(b===button)));
        redraw();
      });
      button.setAttribute("aria-pressed",String(s===current));
      picker.append(button);
    });
    rangeButtons.forEach(b=>b.addEventListener("click",()=>{range=b.dataset.range;from.value="";to.value="";redraw();}));
    from.addEventListener("change",()=>{range="all";redraw();});
    to.addEventListener("change",()=>{range="all";redraw();});
    redraw();
  });
})();