# -*- coding: utf-8 -*-
"""Tous Board — 회의 실시간 관전 웹 콘솔.

브라우저에서 안건을 넣고 회의를 열면, 임원 발언이 완료되는 대로
채팅창처럼 화면에 실시간으로 나타난다. tous.py의 meeting_stream을 그대로 쓴다.
외부 의존성 없음(파이썬 내장 http.server + SSE).

    python board.py            # http://localhost:7000
"""
import os, sys, json, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tous  # noqa: E402  (경로 주입 후 임포트)

PORT = 7000
# 다시보기: 회의 이벤트에 경과시간(t)을 찍어 저장 → /replay 페이지가 채팅 애니로 재생.
# 라이브 화면 녹화 대신 이 타임라인을 다시보기해 mp4로 뽑으면 죽은 구간(CLI 대기)을 압축할 수 있다.
REPLAY_DIR = os.path.join(tous.MEETINGS, "replay")

PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tous 관전 콘솔</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--line:#262b36;--txt:#e6e8ee;--dim:#8b93a3;
 --cto:#a78bfa;--cmo:#34d399;--cso:#60a5fa;--ceo:#f59e0b;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
 font-family:'Segoe UI',system-ui,-apple-system,sans-serif;height:100vh;display:flex;flex-direction:column}
header{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px}
header b{font-size:16px}
#status{margin-left:auto;color:var(--dim);font-size:13px}
#feed{flex:1;overflow-y:auto;padding:18px;display:flex;flex-direction:column;gap:14px}
.sys{align-self:center;color:var(--dim);font-size:12px;background:var(--panel);
 padding:5px 12px;border-radius:20px;border:1px solid var(--line)}
.msg{max-width:760px;width:100%;background:var(--panel);border:1px solid var(--line);
 border-radius:12px;padding:12px 14px;animation:pop .18s ease}
@keyframes pop{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.msg .who{display:flex;align-items:center;gap:8px;margin-bottom:7px;font-size:13px;font-weight:700}
.dot{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;
 font-size:11px;font-weight:800;color:#0f1115}
.msg .body{white-space:pre-wrap;line-height:1.62;font-size:14.5px}
.msg.fail .body{color:var(--dim);font-style:italic}
.msg.tasks{border-color:#3a3f2a;background:#1a1d15}
.msg.tasks .who{color:#d9d574}
.phase{align-self:stretch;display:flex;align-items:center;gap:12px;color:var(--dim);
 font-size:12px;font-weight:700;letter-spacing:.05em;margin:4px 0}
.phase::before,.phase::after{content:'';flex:1;height:1px;background:var(--line)}
.carry{max-width:760px;width:100%;background:#1a1a12;border:1px solid #4a4326;
 border-radius:12px;padding:11px 14px;font-size:13px;line-height:1.6;color:#d6d3a8;white-space:pre-wrap}
.quorum{align-self:center;color:var(--dim);font-size:12px;background:var(--panel);
 padding:6px 14px;border-radius:20px;border:1px solid var(--line);font-weight:600}
.brief{max-width:760px;width:100%;background:#101c26;border:1px solid #2c4a5e;
 border-radius:12px;padding:14px 16px;font-size:14px;line-height:1.7;white-space:pre-wrap}
.motion{max-width:760px;width:100%;background:#1a1728;border:1px solid #3b2f5e;
 border-radius:12px;padding:12px 14px;font-size:14.5px;line-height:1.6}
.motion b{color:var(--cto);display:block;margin-bottom:5px;font-size:12px;letter-spacing:.05em}
.vote{max-width:760px;width:100%;display:flex;align-items:center;gap:10px;
 background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:9px 13px;font-size:14px}
.vote .st{font-weight:800;padding:2px 9px;border-radius:6px;font-size:12px;color:#0f1115}
.vote .st.y{background:#34d399}.vote .st.n{background:#f87171}.vote .st.a{background:#6b7280;color:#e6e8ee}
.vote .rs{color:var(--dim);font-size:13px}
.verdict{max-width:760px;width:100%;text-align:center;padding:13px;border-radius:12px;
 font-size:16px;font-weight:800;border:1px solid}
.verdict.pass{background:#12261c;border-color:#2f6b4b;color:#4ade80}
.verdict.fail{background:#2a1618;border-color:#7f3336;color:#f87171}
.verdict .sub{display:block;font-size:12px;font-weight:600;color:var(--dim);margin-top:5px}
.typing .body{color:var(--dim)}
.typing .body::after{content:'●';animation:blink 1s steps(1) infinite}
@keyframes blink{50%{opacity:.2}}
footer{border-top:1px solid var(--line);padding:12px 16px;display:flex;gap:10px}
#agenda{flex:1;background:var(--panel);border:1px solid var(--line);color:var(--txt);
 border-radius:10px;padding:11px 13px;font-size:14px;outline:none}
#agenda:focus{border-color:var(--cto)}
#go{background:var(--cto);color:#0f1115;border:none;border-radius:10px;padding:0 20px;
 font-weight:700;font-size:14px;cursor:pointer}
#go:disabled{opacity:.45;cursor:not-allowed}
</style></head><body>
<header><b>Tous</b><span style="color:var(--dim);font-size:13px">AI 임원 회의 관전 콘솔</span>
<span id="status">대기 중</span></header>
<div id="feed"></div>
<footer>
 <input id="agenda" placeholder="안건을 입력하고 Enter — 예: 회사명 Kaelun을 확정할까?" autocomplete="off">
 <button id="go">회의 열기</button>
</footer>
<script>
const META={CTO:{n:'Claude',c:'var(--cto)'},CMO:{n:'ChatGPT',c:'var(--cmo)'},
 CSO:{n:'Copilot',c:'var(--cso)'},CEO:{n:'CEO',c:'var(--ceo)'},
 '고문':{n:'Gemini',c:'#94a3b8'},Research:{n:'Vertex',c:'#fbbf24'}};
const feed=document.getElementById('feed'), statusEl=document.getElementById('status'),
 input=document.getElementById('agenda'), go=document.getElementById('go');
let es=null;
const pad=n=>String(n).padStart(3,'0');
function scroll(){feed.scrollTop=feed.scrollHeight;}
function setStatus(t){statusEl.textContent=t;}
function sys(t){const d=document.createElement('div');d.className='sys';d.textContent=t;feed.appendChild(d);scroll();}
function bubble(role,name,text,ok,cls){
 const m=document.createElement('div');m.className='msg'+(ok===false?' fail':'')+(cls?' '+cls:'');
 const who=document.createElement('div');who.className='who';
 const meta=META[role]||{n:name,c:'var(--dim)'};
 const dot=document.createElement('span');dot.className='dot';dot.style.background=meta.c;
 dot.textContent=/^C[TMSE]O$/.test(role)?role[1]:role[0];  // CTO/CMO/CSO/CEO는 둘째 글자로 구분
 const lbl=document.createElement('span');lbl.style.color=meta.c;
 lbl.textContent=role+' · '+(name||meta.n);
 who.appendChild(dot);who.appendChild(lbl);
 const body=document.createElement('div');body.className='body';body.textContent=text;
 m.appendChild(who);m.appendChild(body);feed.appendChild(m);scroll();return m;
}
function plainCard(cls,text){const d=document.createElement('div');d.className=cls;
 d.textContent=text;feed.appendChild(d);scroll();}
function phaseBar(label){const d=document.createElement('div');d.className='phase';
 d.textContent=label;feed.appendChild(d);scroll();}
function motionCard(text){const d=document.createElement('div');d.className='motion';
 const b=document.createElement('b');b.textContent='표결에 부쳐진 동의안';
 const s=document.createElement('span');s.textContent=text;
 d.appendChild(b);d.appendChild(s);feed.appendChild(d);scroll();}
function voteRow(role,name,stance,reason){
 const d=document.createElement('div');d.className='vote';
 const meta=META[role]||{c:'var(--dim)'};
 const who=document.createElement('span');who.style.color=meta.c;who.style.fontWeight='700';
 who.textContent=role+' · '+name;
 const st=document.createElement('span');
 st.className='st '+(stance==='찬성'?'y':stance==='반대'?'n':'a');st.textContent=stance;
 const rs=document.createElement('span');rs.className='rs';rs.textContent=reason;
 d.appendChild(who);d.appendChild(st);d.appendChild(rs);feed.appendChild(d);scroll();}
function verdictCard(d0){
 const d=document.createElement('div');
 const won=d0.verdict==='가결'||/채택/.test(d0.verdict||'');
 d.className='verdict '+(won?'pass':'fail');
 const score=d0.tally
   ? Object.keys(d0.tally).sort().map(k=>k+' '+d0.tally[k]+'표').join(' · ')
   : d0.yes+' : '+d0.nay;
 d.textContent=score+'  '+d0.verdict;
 const s=document.createElement('span');s.className='sub';
 s.textContent=d0.losers&&d0.losers.length
   ? d0.losers.join(', ')+' 반대했으나 결과를 따른다'
   : '전원 일치';
 d.appendChild(s);feed.appendChild(d);scroll();}
let typingEl=null;
function showTyping(role,name){removeTyping();
 typingEl=bubble(role,name,'발언 작성 중…',true,'typing');}
function removeTyping(){if(typingEl){typingEl.remove();typingEl=null;}}
function finish(){go.disabled=false;if(es){es.close();es=null;}}
function handle(d){
 if(d.ev==='open'){setStatus('회의 #'+pad(d.no)+' 진행 중');}
 else if(d.ev==='carryover'){plainCard('carry',d.text);}
 else if(d.ev==='quorum'){plainCard('quorum',d.text);}
 else if(d.ev==='brief'){removeTyping();plainCard('brief',d.text);}
 else if(d.ev==='phase'){removeTyping();phaseBar(d.label);}
 else if(d.ev==='motion'){removeTyping();motionCard(d.text);}
 else if(d.ev==='vote'){removeTyping();voteRow(d.role,d.name,d.stance,d.reason);}
 else if(d.ev==='verdict'){verdictCard(d);}
 else if(d.ev==='asking'){showTyping(d.role,d.name);}
 else if(d.ev==='utterance'){removeTyping();
   bubble(d.role,d.name,d.ok?d.text:'(불참) '+d.text,d.ok);}
 else if(d.ev==='tasks'){if(d.count>0||d.md){
   const m=bubble('CTO','도출된 Task',d.md,true,'tasks');
   m.querySelector('.who span:last-child').textContent='도출된 Task ('+d.count+'건)';}}
 else if(d.ev==='done'){setStatus('회의 #'+pad(d.no)+' 종료 · 참석 '+d.present.length+'/'+d.total);
   sys('회의록 저장 완료 · '+d.tasks+'건 Task 생성');
   const a=document.createElement('a');a.href='/replay?no='+d.no;a.target='_blank';
   a.className='sys';a.style.color='var(--cto)';a.style.textDecoration='none';
   a.textContent='▶ 이 회의 다시보기';feed.appendChild(a);scroll();finish();}
 else if(d.ev==='error'){sys('오류: '+d.msg);finish();}
 else if(d.ev==='closed'){finish();}
}
function open(){
 const a=input.value.trim();if(!a)return;
 if(es)es.close();feed.innerHTML='';go.disabled=true;
 setStatus('연결 중…');sys('회의를 소집합니다 — “'+a+'”');
 es=new EventSource('/stream?agenda='+encodeURIComponent(a));
 es.onmessage=e=>handle(JSON.parse(e.data));
 es.onerror=()=>{setStatus('연결 종료');finish();};
}
go.onclick=open;
input.addEventListener('keydown',e=>{if(e.key==='Enter')open();});
</script></body></html>"""


REPLAY_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tous 회의 다시보기</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--line:#262b36;--txt:#e6e8ee;--dim:#8b93a3;
 --cto:#a78bfa;--cmo:#34d399;--cso:#60a5fa;--ceo:#f59e0b;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
 font-family:'Segoe UI',system-ui,-apple-system,sans-serif;height:100vh;display:flex;flex-direction:column}
header{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px}
header b{font-size:16px}
#status{margin-left:auto;color:var(--dim);font-size:13px}
.ctl{display:flex;gap:8px;align-items:center}
.ctl button{background:var(--panel);border:1px solid var(--line);color:var(--txt);
 border-radius:8px;padding:6px 12px;font-size:13px;cursor:pointer}
#feed{flex:1;overflow-y:auto;padding:18px;display:flex;flex-direction:column;gap:14px}
.sys{align-self:center;color:var(--dim);font-size:12px;background:var(--panel);
 padding:5px 12px;border-radius:20px;border:1px solid var(--line)}
.msg{max-width:760px;width:100%;background:var(--panel);border:1px solid var(--line);
 border-radius:12px;padding:12px 14px;animation:pop .18s ease}
@keyframes pop{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.msg .who{display:flex;align-items:center;gap:8px;margin-bottom:7px;font-size:13px;font-weight:700}
.dot{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;
 font-size:11px;font-weight:800;color:#0f1115}
.msg .body{white-space:pre-wrap;line-height:1.62;font-size:14.5px}
.msg.fail .body{color:var(--dim);font-style:italic}
.msg.tasks{border-color:#3a3f2a;background:#1a1d15}
.phase{align-self:stretch;display:flex;align-items:center;gap:12px;color:var(--dim);
 font-size:12px;font-weight:700;letter-spacing:.05em;margin:4px 0}
.phase::before,.phase::after{content:'';flex:1;height:1px;background:var(--line)}
.carry{max-width:760px;width:100%;background:#1a1a12;border:1px solid #4a4326;
 border-radius:12px;padding:11px 14px;font-size:13px;line-height:1.6;color:#d6d3a8;white-space:pre-wrap}
.quorum{align-self:center;color:var(--dim);font-size:12px;background:var(--panel);
 padding:6px 14px;border-radius:20px;border:1px solid var(--line);font-weight:600}
.brief{max-width:760px;width:100%;background:#101c26;border:1px solid #2c4a5e;
 border-radius:12px;padding:14px 16px;font-size:14px;line-height:1.7;white-space:pre-wrap}
.motion{max-width:760px;width:100%;background:#1a1728;border:1px solid #3b2f5e;
 border-radius:12px;padding:12px 14px;font-size:14.5px;line-height:1.6}
.motion b{color:var(--cto);display:block;margin-bottom:5px;font-size:12px;letter-spacing:.05em}
.vote{max-width:760px;width:100%;display:flex;align-items:center;gap:10px;
 background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:9px 13px;font-size:14px}
.vote .st{font-weight:800;padding:2px 9px;border-radius:6px;font-size:12px;color:#0f1115}
.vote .st.y{background:#34d399}.vote .st.n{background:#f87171}.vote .st.a{background:#6b7280;color:#e6e8ee}
.vote .rs{color:var(--dim);font-size:13px}
.verdict{max-width:760px;width:100%;text-align:center;padding:13px;border-radius:12px;
 font-size:16px;font-weight:800;border:1px solid}
.verdict.pass{background:#12261c;border-color:#2f6b4b;color:#4ade80}
.verdict.fail{background:#2a1618;border-color:#7f3336;color:#f87171}
.verdict .sub{display:block;font-size:12px;font-weight:600;color:var(--dim);margin-top:5px}
.typing .body{color:var(--dim)}
.typing .body::after{content:'●';animation:blink 1s steps(1) infinite}
@keyframes blink{50%{opacity:.2}}
</style></head><body>
<header><b>Tous</b><span style="color:var(--dim);font-size:13px">회의 다시보기</span>
<span class="ctl"><button id="rec">⏺ 녹화</button><button id="restart">↻ 처음부터</button></span>
<span id="status">불러오는 중…</span></header>
<div id="feed"></div>
<script>
const META={CTO:{n:'Claude',c:'var(--cto)'},CMO:{n:'ChatGPT',c:'var(--cmo)'},
 CSO:{n:'Copilot',c:'var(--cso)'},CEO:{n:'CEO',c:'var(--ceo)'},
 '고문':{n:'Gemini',c:'#94a3b8'},Research:{n:'Vertex',c:'#fbbf24'}};
const feed=document.getElementById('feed'), statusEl=document.getElementById('status');
const pad=n=>String(n).padStart(3,'0');
const GAP_CAP=1.2;  // CLI 대기 등 죽은 구간을 최대 1.2초로 압축
function scroll(){feed.scrollTop=feed.scrollHeight;}
function sys(t){const d=document.createElement('div');d.className='sys';d.textContent=t;feed.appendChild(d);scroll();}
function bubble(role,name,text,ok,cls){
 const m=document.createElement('div');m.className='msg'+(ok===false?' fail':'')+(cls?' '+cls:'');
 const who=document.createElement('div');who.className='who';
 const meta=META[role]||{n:name,c:'var(--dim)'};
 const dot=document.createElement('span');dot.className='dot';dot.style.background=meta.c;
 dot.textContent=/^C[TMSE]O$/.test(role)?role[1]:role[0];
 const lbl=document.createElement('span');lbl.style.color=meta.c;lbl.textContent=role+' · '+(name||meta.n);
 who.appendChild(dot);who.appendChild(lbl);
 const body=document.createElement('div');body.className='body';body.textContent=text;
 m.appendChild(who);m.appendChild(body);feed.appendChild(m);scroll();return m;
}
function plainCard(cls,text){const d=document.createElement('div');d.className=cls;
 d.textContent=text;feed.appendChild(d);scroll();}
function phaseBar(label){const d=document.createElement('div');d.className='phase';
 d.textContent=label;feed.appendChild(d);scroll();}
function motionCard(text){const d=document.createElement('div');d.className='motion';
 const b=document.createElement('b');b.textContent='표결에 부쳐진 동의안';
 const s=document.createElement('span');s.textContent=text;
 d.appendChild(b);d.appendChild(s);feed.appendChild(d);scroll();}
function voteRow(role,name,stance,reason){
 const d=document.createElement('div');d.className='vote';
 const meta=META[role]||{c:'var(--dim)'};
 const who=document.createElement('span');who.style.color=meta.c;who.style.fontWeight='700';
 who.textContent=role+' · '+name;
 const st=document.createElement('span');
 st.className='st '+(stance==='찬성'?'y':stance==='반대'?'n':'a');st.textContent=stance;
 const rs=document.createElement('span');rs.className='rs';rs.textContent=reason;
 d.appendChild(who);d.appendChild(st);d.appendChild(rs);feed.appendChild(d);scroll();}
function verdictCard(d0){
 const d=document.createElement('div');
 const won=d0.verdict==='가결'||/채택/.test(d0.verdict||'');
 d.className='verdict '+(won?'pass':'fail');
 const score=d0.tally
   ? Object.keys(d0.tally).sort().map(k=>k+' '+d0.tally[k]+'표').join(' · ')
   : d0.yes+' : '+d0.nay;
 d.textContent=score+'  '+d0.verdict;
 const s=document.createElement('span');s.className='sub';
 s.textContent=d0.losers&&d0.losers.length
   ? d0.losers.join(', ')+' 반대했으나 결과를 따른다'
   : '전원 일치';
 d.appendChild(s);feed.appendChild(d);scroll();}
let typingEl=null;
function showTyping(role,name){removeTyping();typingEl=bubble(role,name,'발언 작성 중…',true,'typing');}
function removeTyping(){if(typingEl){typingEl.remove();typingEl=null;}}
function render(ev,data){
 if(ev==='open'){setStatus('회의 #'+pad(data.no)+' 다시보기');sys('안건 — “'+data.agenda+'”');}
 else if(ev==='carryover'){plainCard('carry',data.text);}
 else if(ev==='quorum'){plainCard('quorum',data.text);}
 else if(ev==='brief'){removeTyping();plainCard('brief',data.text);}
 else if(ev==='phase'){removeTyping();phaseBar(data.label);}
 else if(ev==='motion'){removeTyping();motionCard(data.text);}
 else if(ev==='vote'){removeTyping();voteRow(data.role,data.name,data.stance,data.reason);}
 else if(ev==='verdict'){verdictCard(data);}
 else if(ev==='asking'){showTyping(data.role,data.name);}
 else if(ev==='utterance'){removeTyping();bubble(data.role,data.name,data.ok?data.text:'(불참) '+data.text,data.ok);}
 else if(ev==='tasks'){if(data.count>0||data.md){const m=bubble('CTO','도출된 Task',data.md,true,'tasks');
   m.querySelector('.who span:last-child').textContent='도출된 Task ('+data.count+'건)';}}
 else if(ev==='done'){setStatus('회의 #'+pad(data.no)+' · 참석 '+data.present.length+'/'+data.total+' · 재생 완료');
   if(mediaRec)setTimeout(()=>{if(mediaRec)mediaRec.stop();},1500);}  // 녹화 중이면 재생 종료 후 자동 정지
}
function setStatus(t){statusEl.textContent=t;}

// 화면 녹화 — getDisplayMedia로 탭을 캡처하며 다시보기를 처음부터 재생, 종료 시 webm 저장.
// (브라우저 표준 포맷은 webm. mp4가 필요하면 ffmpeg로 변환.)
const recBtn=document.getElementById('rec');
let mediaRec=null,chunks=[];
function pickMime(){for(const m of ['video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm']){
 if(window.MediaRecorder&&MediaRecorder.isTypeSupported(m))return m;}return '';}
async function record(){
 if(mediaRec){mediaRec.stop();return;}
 if(!navigator.mediaDevices||!navigator.mediaDevices.getDisplayMedia){
   setStatus('이 브라우저는 화면 녹화를 지원하지 않습니다');return;}
 try{
  const stream=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:30},audio:false});
  const mime=pickMime();chunks=[];
  mediaRec=new MediaRecorder(stream,mime?{mimeType:mime}:undefined);
  mediaRec.ondataavailable=e=>{if(e.data&&e.data.size)chunks.push(e.data);};
  mediaRec.onstop=()=>{stream.getTracks().forEach(t=>t.stop());
   const blob=new Blob(chunks,{type:'video/webm'});const a=document.createElement('a');
   a.href=URL.createObjectURL(blob);a.download='meeting-'+(no||'x')+'.webm';a.click();
   recBtn.textContent='⏺ 녹화';mediaRec=null;};
  mediaRec.start();recBtn.textContent='■ 녹화 중지';play();  // 녹화 시작과 동시에 처음부터
 }catch(err){setStatus('녹화 취소/실패: '+err.message);mediaRec=null;}
}
recBtn.onclick=record;
let EVENTS=[];
// ?stop=<이벤트명> 을 붙이면 그 이벤트까지만 재생하고 멈춘다(스크린샷용).
const STOP_AT=new URLSearchParams(location.search).get('stop');
function play(){
 feed.innerHTML='';removeTyping();
 let i=0,prev=0;
 (function step(){
   if(i>=EVENTS.length)return;
   const e=EVENTS[i++];
   if(STOP_AT&&EVENTS[i-2]&&EVENTS[i-2].ev===STOP_AT){removeTyping();return;}
   const wait=i===1?0:Math.min(Math.max(e.t-prev,0),GAP_CAP)*1000;prev=e.t;
   setTimeout(()=>{render(e.ev,e.data);step();},wait);
 })();
}
document.getElementById('restart').onclick=play;
const no=new URLSearchParams(location.search).get('no');
fetch('/replay-data?no='+encodeURIComponent(no)).then(r=>{
 if(!r.ok)throw new Error('저장된 다시보기가 없습니다 (회의 #'+no+')');return r.json();
}).then(d=>{EVENTS=d.events;play();}).catch(e=>{setStatus(e.message);});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 콘솔 소음 억제
        pass

    def _html(self, body):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _push(self, ev, data):
        payload = json.dumps({"ev": ev, **data}, ensure_ascii=False)
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _save_replay(self, no, agenda, rec):
        """완주한 회의의 이벤트 타임라인을 저장(다시보기용). 부분 회의는 저장 안 함."""
        if not no:
            return
        os.makedirs(REPLAY_DIR, exist_ok=True)
        path = os.path.join(REPLAY_DIR, f"meeting-{no:03d}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"no": no, "agenda": agenda, "events": rec}, f,
                      ensure_ascii=False, indent=2)

    def _stream(self, agenda):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        if not agenda:
            self._push("error", {"msg": "안건이 비어 있습니다."})
            return
        rec, t0, no = [], time.monotonic(), None   # 이벤트에 경과시간을 찍어 다시보기로 저장
        try:
            for ev, data in tous.meeting_stream(agenda):
                rec.append({"t": round(time.monotonic() - t0, 2), "ev": ev, "data": data})
                if "no" in data:
                    no = data["no"]
                if ev == "done":
                    self._save_replay(no, agenda, rec)
                self._push(ev, data)
        except (BrokenPipeError, ConnectionAbortedError):
            return  # 브라우저가 창을 닫음 — 조용히 종료
        except Exception as e:
            try:
                self._push("error", {"msg": str(e)})
            except Exception:
                return
        try:
            self._push("closed", {})
        except Exception:
            pass

    def _replay_data(self, no):
        try:
            n = int(no)
        except (ValueError, TypeError):
            self.send_error(400); return
        path = os.path.join(REPLAY_DIR, f"meeting-{n:03d}.json")
        if not os.path.exists(path):
            self.send_error(404); return
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._html(PAGE)
        elif u.path == "/replay":
            self._html(REPLAY_PAGE)
        elif u.path == "/replay-data":
            self._replay_data(parse_qs(u.query).get("no", [""])[0])
        elif u.path == "/stream":
            agenda = parse_qs(u.query).get("agenda", [""])[0].strip()
            self._stream(agenda)
        else:
            self.send_error(404)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Tous Board → http://localhost:{PORT}  (Ctrl+C 종료)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")
        srv.shutdown()


if __name__ == "__main__":
    main()
