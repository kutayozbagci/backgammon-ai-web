// ----- CONFIG -----
const API = "http://127.0.0.1:8010";
console.log("app.js loaded", new Date().toISOString());

// ----- STATE -----
let game_id = null, dice = null, state = null, legalPaths = [], selectedPathIdx = null;

// ----- DOM helpers -----
const $ = (id) => document.getElementById(id);
const setDice = (d) => $("dice").textContent = "dice: " + (d ? `${d[0]} + ${d[1]}` : "–");
const setBtns = () => { $("human").disabled = !(selectedPathIdx !== null && dice && game_id); $("ai").disabled = !(dice && game_id); };

// ----- API -----
async function post(url, body) {
  const r = await fetch(API + url, { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(body||{}) });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ----- Board rendering -----
let svg;  // will be set after DOM is ready

const W=1000,H=600,padding=20,boardW=W-padding*2,boardH=H-padding*2,barW=60,trayW=80,playW=boardW-trayW*2,halfW=(playW-barW)/2,triH=boardH/2-20,pointW=halfW/12;
const COLOR_BOARD="#0b1220",COLOR_BORDER="#0b213d",COLOR_TRIA="#1f2937",COLOR_TRIB="#374151",COLOR_BAR="#0a0f1a",COLOR_BAR_OUT="#16263e",COLOR_TRAY="#0a1020",COLOR_TRAY_O="#15223a",COLOR_OWN="#3b82f6",COLOR_OPP="#ef4444",COLOR_HALO="#f59e0b",COLOR_STROKE="#0b1324",COLOR_LABEL="#95a3b8";
const svgNS="http://www.w3.org/2000/svg";
function clearSVG(){ while(svg.firstChild) svg.removeChild(svg.firstChild); }
function make(tag, attrs={}, parent=svg){ const e=document.createElementNS(svgNS,tag); for(const k in attrs) e.setAttribute(k,attrs[k]); parent.appendChild(e); return e; }

function drawBoardBase(){
  clearSVG();
  make("rect",{x:padding,y:padding,width:boardW,height:boardH,rx:16,fill:COLOR_BOARD,stroke:COLOR_BORDER,"stroke-width":2});
  make("rect",{x:padding,y:padding,width:trayW,height:boardH,rx:12,fill:COLOR_TRAY,stroke:COLOR_TRAY_O});
  make("rect",{x:padding+boardW-trayW,y:padding,width:trayW,height:boardH,rx:12,fill:COLOR_TRAY,stroke:COLOR_TRAY_O});

  const barX=padding+trayW+halfW, barXc=barX+barW/2;
  make("rect",{x:barX,y:padding,width:barW,height:boardH,fill:COLOR_BAR,stroke:COLOR_BAR_OUT});

  const drawRow=(row)=>{
    for(let col=0; col<12; col++){
      const x0=padding+trayW+col*pointW+(col>=6?barW:0), x1=x0+pointW, xMid=(x0+x1)/2;
      const points=row==="top" ? `${x0},${padding} ${x1},${padding} ${xMid},${padding+triH}` : `${x0},${padding+boardH} ${x1},${padding+boardH} ${xMid},${padding+boardH-triH}`;
      const fill=(col%2===0)?COLOR_TRIA:COLOR_TRIB;
      make("polygon",{points,fill,stroke:"#0e1625","stroke-width":1});
    }
  };
  drawRow("top"); drawRow("bot");

  const label=(t,x,y)=>{ const e=make("text",{x,y,"text-anchor":"middle","dominant-baseline":"central",fill:COLOR_LABEL,"font-size":"12"}); e.textContent=t; };
  const topPts=[13,14,15,16,17,18,19,20,21,22,23,24], botPts=[12,11,10,9,8,7,6,5,4,3,2,1];
  topPts.forEach((p,i)=>{ const x0=padding+trayW+i*pointW+(i>=6?barW:0); label(p,x0+pointW/2,padding+10); });
  botPts.forEach((p,i)=>{ const x0=padding+trayW+i*pointW+(i>=6?barW:0); label(p,x0+pointW/2,padding+boardH-10); });

  // trays
  let t1=make("text",{x:padding+10,y:padding+18,fill:COLOR_LABEL,"font-size":"12"}); t1.textContent="Opp off";
  let t2=make("text",{x:padding+boardW-trayW+10,y:padding+18,fill:COLOR_LABEL,"font-size":"12"}); t2.textContent="Your off";

  // bars centered vertically
  const midY = padding + boardH/2;
  make("text",{x:barXc,y:midY-12,fill:COLOR_LABEL,"font-size":"12","text-anchor":"middle"}).textContent="Opp bar";
  make("text",{x:barXc,y:midY+12,fill:COLOR_LABEL,"font-size":"12","text-anchor":"middle"}).textContent="Your bar";
}

// helper to draw borne-off stacks into the side trays
function drawOffStack(count, side){
  const x = side==='opp' ? (padding+trayW/2) : (padding+boardW-trayW/2);
  const startY = side==='opp' ? (padding+26) : (padding+boardH-26);
  const step = side==='opp' ? 28 : -28;
  const color = side==='opp' ? COLOR_OPP : COLOR_OWN;
  const capped = Math.min(count,5);
  for (let i=0;i<capped;i++) drawChecker(x, startY + i*step, color);
  if (count>5) drawChecker(x, startY + (capped-1)*step, color, `+${count-5}`);
}

function drawChecker(x,y,color,text=null,glow=false){
  make("circle",{cx:x,cy:y,r:14,fill:color,stroke:glow?COLOR_HALO:COLOR_STROKE,"stroke-width":glow?4:2});
  if(text){ const t=make("text",{x,y,"text-anchor":"middle","dominant-baseline":"central",fill:"#061426","font-size":"12","font-weight":"700"}); t.textContent=text; }
}
function drawStack(row,col,count,color){
  const baseX=padding+trayW+col*pointW+(col>=6?barW:0)+pointW/2, startY=(row==="top")?(padding+26):(padding+boardH-26), step=(row==="top")?28:-28;
  const capped=Math.min(count,5);
  for(let i=0;i<capped;i++) drawChecker(baseX,startY+i*step,color);
  if(count>5) drawChecker(baseX,startY+(capped-1)*step,color,`+${count-5}`);
}
const idxFromPoint=(p)=>28-p, pointFromIdx=(i)=>28-i, entryPointFromDie=(d)=>25-d;
function pointToRowCol(p){ return (p>=13&&p<=24)?{row:"top",col:(p-13)}:{row:"bot",col:(12-p)}; }

function drawFromState(s, highlightPath=null){
  drawBoardBase();

  // side panel counts
  $("own_broken").textContent=s[0]; $("own_off").textContent=s[1];
  $("opp_broken").textContent=s[2]; $("opp_off").textContent=s[3];

  // board points
  const top=[13,14,15,16,17,18,19,20,21,22,23,24], bot=[12,11,10,9,8,7,6,5,4,3,2,1];
  top.forEach((p,i)=>{ const idx=idxFromPoint(p), v=s[idx]; if(v>0) drawStack("top",i,v,COLOR_OWN); else if(v<0) drawStack("top",i,-v,COLOR_OPP); });
  bot.forEach((p,i)=>{ const idx=idxFromPoint(p), v=s[idx]; if(v>0) drawStack("bot",i,v,COLOR_OWN); else if(v<0) drawStack("bot",i,-v,COLOR_OPP); });

  // bars centered around midline
  const barX=padding+trayW+halfW+barW/2, midY=padding+boardH/2, gap=18, step=28;

  const ob=Math.min(s[2],5);
  for(let i=0;i<ob;i++) drawChecker(barX, midY - gap - i*step, COLOR_OPP);
  if(s[2]>5) drawChecker(barX, midY - gap - 4*step, COLOR_OPP, `+${s[2]-5}`);

  const hb=Math.min(s[0],5);
  for(let i=0;i<hb;i++) drawChecker(barX, midY + gap + i*step, COLOR_OWN);
  if(s[0]>5) drawChecker(barX, midY + gap + 4*step, COLOR_OWN, `+${s[0]-5}`);

  // borne-off piles visible in trays
  drawOffStack(s[3], 'opp');
  drawOffStack(s[1], 'own');

  // highlight preview
  if(highlightPath&&highlightPath.length){
    for(const [idx,die,t] of highlightPath){
      if(t===0){
        const pFrom=pointFromIdx(idx), pTo=pointFromIdx(idx+die), a=pointToRowCol(pFrom), b=pointToRowCol(pTo);
        const xA=padding+trayW+a.col*pointW+(a.col>=6?barW:0)+pointW/2, yA=(a.row==="top")?(padding+26):(padding+boardH-26);
        const xB=padding+trayW+b.col*pointW+(b.col>=6?barW:0)+pointW/2, yB=(b.row==="top")?(padding+26):(padding+boardH-26);
        make("circle",{cx:xA,cy:yA,r:18,fill:"none",stroke:COLOR_HALO,"stroke-width":3,"stroke-opacity":0.7});
        make("circle",{cx:xB,cy:yB,r:18,fill:"none",stroke:COLOR_HALO,"stroke-width":3,"stroke-opacity":0.7});
      } else if(t===-1){
        const p=pointFromIdx(idx), a=pointToRowCol(p);
        const xA=padding+trayW+a.col*pointW+(a.col>=6?barW:0)+pointW/2, yA=(a.row==="top")?(padding+26):(padding+boardH-26);
        make("circle",{cx:xA,cy:yA,r:18,fill:"none",stroke:COLOR_HALO,"stroke-width":3,"stroke-opacity":0.7});
      } else if(t===1){
        const pTo=entryPointFromDie(die), b=pointToRowCol(pTo);
        const xB=padding+trayW+b.col*pointW+(b.col>=6?barW:0)+pointW/2, yB=(b.row==="top")?(padding+26):(padding+boardH-26);
        make("circle",{cx:xB,cy:yB,r:18,fill:"none",stroke:COLOR_HALO,"stroke-width":3,"stroke-opacity":0.7});
      }
    }
  }
}

// ----- Paths UI -----
function fmtStep([idx,die,t]){
  if(t===1){ const p=entryPointFromDie(die); return `BAR→${p} (die ${die})`; }
  if(t===-1){ const p=pointFromIdx(idx), exact=(idx===28-die); return exact?`${p}→OFF (die ${die})`:`${p}→OFF (oversize ${die})`; }
  const pFrom=pointFromIdx(idx), pTo=pointFromIdx(idx+die); return `${pFrom}→${pTo} (die ${die})`;
}

// PASS support: pretty-print empty path
function fmtPath(path){
  if (!path || path.length === 0) return "PASS (no legal moves)";
  return path.map(fmtStep).join("  ·  ");
}

function renderPaths(){
  const container = $("paths");
  container.innerHTML = "";
  if (!Array.isArray(legalPaths) || legalPaths.length === 0) legalPaths = [[]]; // PASS

  legalPaths.forEach((p,i) => {
    const isPass = Array.isArray(p) && p.length === 0;
    const div = document.createElement("div");
    div.className = "path-item" + (selectedPathIdx === i ? " active" : "");
    div.textContent = isPass ? "PASS (no legal moves)" : fmtPath(p);
    div.onclick = () => selectPath(i);
    container.appendChild(div);
  });
}

let turn = null;
function reflectTurn(){
  if (turn === "HUMAN") {
    $("human").disabled = !(selectedPathIdx !== null && dice && game_id);
    $("ai").disabled    = true;
  } else if (turn === "AI") {
    $("human").disabled = true;
    $("ai").disabled    = !(dice && game_id);
  } else {
    // unknown -> fall back, still usable
    $("human").disabled = !(selectedPathIdx !== null && dice && game_id);
    $("ai").disabled    = !(dice && game_id);
  }
}

// ----- Wire up after DOM is ready -----
document.addEventListener("DOMContentLoaded", () => {
  svg = $("board");
  $("new").onclick = async () => {
      if (!confirm("Start a new game? Current game will be lost.")) return;
  try {
      const ai_side = $("ai_side").value;
      const j = await post("/game/new", { ai_side });
      console.log("NEW GAME response:", j);
      const gid = j.game_id ?? j.id ?? j.gid ?? j.session_id ?? j.gameId ?? null;
      const st  = j.state ?? j.board ?? j.s ?? null;
      if (!gid) { alert("Backend didn't return a game id. Response: " + JSON.stringify(j)); return; }
      if (!st)  { alert("Backend didn't return a state. Response: " + JSON.stringify(j)); return; }
      game_id = gid; state = st; dice = null; legalPaths = []; selectedPathIdx = null;
      setDice(null); setBtns(); drawFromState(state); renderPaths();
    } catch (e) {
      console.error(e); alert("New Game error: " + e);
    }
  };

  $("roll").onclick = async () => {
  if(!game_id) return alert("Start a game first");
  try {
    const j = await post("/game/roll",{game_id});
    dice = j.dice; setDice(dice); setBtns();

    const leg = await post("/game/legal",{game_id});
    legalPaths = leg.paths || [];
    if (!Array.isArray(legalPaths) || legalPaths.length === 0) legalPaths = [[]];
    renderPaths();
    renderPaths();

    if (legalPaths.length === 1) {
      // Let the DOM paint, then dispatch a real click so your onclick runs.
      requestAnimationFrame(() => {
        const first = $("paths").querySelector(".path-item");
        if (first) {
          first.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        }
      });
    }
  } catch(e){ alert(e); }
};
    
  $("refresh").onclick = async () => {
  if(!game_id) return;
  if(!dice) return alert("Roll first");
  try {
    const leg = await post("/game/legal",{game_id});
    legalPaths = leg.paths || [];
    
    if (!Array.isArray(legalPaths) || legalPaths.length === 0) legalPaths = [[]];
    renderPaths();
    if (legalPaths.length === 1) {
      // Let the DOM paint, then dispatch a real click so your onclick runs.
      requestAnimationFrame(() => {
        const first = $("paths").querySelector(".path-item");
        if (first) {
          first.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        }
      });
    }
  } catch(e){ alert(e); }
};

  $("human").onclick = async () => {
    if(selectedPathIdx===null) return alert("Pick a path first");
    try {
      const path = legalPaths[selectedPathIdx];           // [] means PASS
      const j = await post("/game/move/human",{game_id,dice,path});
      state = j.state;
      dice = null; setDice(null);
      legalPaths = []; selectedPathIdx = null; setBtns();
      drawFromState(state); renderPaths();
      if(j.done) alert("You bore off all — GG!");
    } catch(e){ alert(e); }
  };

  $("ai").onclick = async () => {
    if(!dice) return alert("Roll first");
    try {
      const j = await post("/game/move/ai",{game_id,dice});
      state = j.state; dice = null; setDice(null); setBtns(); drawFromState(state);
      if(j.path && j.path.length){ legalPaths=[j.path]; selectedPathIdx=0; renderPaths(); }
      else { legalPaths=[]; selectedPathIdx=null; renderPaths(); }
      if(j.done) alert("AI bore off all — GG!");
    } catch(e){ alert(e); }
  };

  // initial paint
  drawFromState([0,0,0,0, 2,0,0,0,0,-5,0,-3,0,0,0,5,-5,0,0,0,3,0,5,0,0,0,0,-2]);
  setBtns();
});

function autoSelectIfSingle() {
  if (!Array.isArray(legalPaths)) legalPaths = [];
  if (legalPaths.length === 0) legalPaths = [[]];       // normalize PASS
  selectedPathIdx = (legalPaths.length === 1 ? 0 : null);
  renderPaths();
  drawFromState(state, selectedPathIdx !== null ? legalPaths[selectedPathIdx] : null);
  setBtns(); // or reflectTurn() if you're using turn-gating
}

function selectPath(i){
  selectedPathIdx = i;
  drawFromState(state, legalPaths[i]);
  renderPaths();
  reflectTurn();
}
