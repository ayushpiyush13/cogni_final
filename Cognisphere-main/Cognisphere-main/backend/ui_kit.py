"""CropShield "NEON FIELD" UI kit (performance build) - animated vector scenery, aurora, spores, glowing cards.

Drop-in replacement: same helpers as before (esc, inject_css, hero, card, pill, meter, facts, rows,
coming_soon) so main.py works unchanged. Pure CSS + inline SVG, no JavaScript.

Performance rules used here:
  * continuous animations only touch transform / opacity (GPU-composited, no repaint)
  * costly effects (animated borders, glows, sweeps) run on hover only
  * the SVG scenery uses few animated nodes (wheat is animated in 3 groups, not per stalk)
  * the wheat/hills scene is its own band BELOW the hero text, so it can never cover text
"""
import html
import math
import random

import streamlit as st

# ---------------------------------------------------------------- tiny SVG tiles used as backgrounds
LEAF_TILE = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200' "
             "viewBox='0 0 200 200'><g fill='none' stroke='%234ade80' stroke-opacity='.55' stroke-width='1.2' "
             "stroke-linecap='round' stroke-linejoin='round'><path d='M30 50c14-22 40-22 50-4-20 14-40 14-50 4z'/>"
             "<path d='M30 50l44-14'/><path d='M120 130c10-26 38-34 52-14-16 20-38 26-52 14z'/><path d='M120 130l46-20'/>"
             "<circle cx='150' cy='40' r='3'/><circle cx='60' cy='150' r='2.5'/><path d='M96 20q6 8 0 16q-6-8 0-16z'/>"
             "<path d='M20 160q6 8 0 16q-6-8 0-16z'/><path d='M170 170l8-8m-8 0l8 8'/></g></svg>")
HEX_TILE = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='56' height='100' "
            "viewBox='0 0 56 100'><g fill='none' stroke='%2322c55e' stroke-opacity='.45' stroke-width='1'>"
            "<path d='M28 66L0 50V16L28 0l28 16v34zM28 100L0 84V50M28 100l28-16V50'/></g></svg>")
CORNER_LEAF = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='80' height='80' "
               "viewBox='0 0 80 80'><g fill='none' stroke='%234ade80' stroke-width='1.6' stroke-linecap='round'>"
               "<path d='M10 70C8 40 30 14 70 10c2 36-18 58-60 60z'/><path d='M10 70L58 22'/><path d='M28 52l14 2'/>"
               "<path d='M38 42l14 2'/><path d='M22 60l2-14'/></g></svg>")

CSS = """<style>
/* ===== CropShield NEON FIELD (performance build) ===== */
:root{--bg:#000;--s1:#0a100c;--s2:#101812;--s3:#16221a;--line:#1b2a20;--line2:#27432f;--tx:#eef8f1;--mut:#8ba597;
--g1:#16a34a;--g2:#22c55e;--g3:#4ade80;--r:22px;--pad:clamp(14px,4vw,28px)}
@property --ang{syntax:'<angle>';inherits:false;initial-value:210deg}
html{font-size:clamp(17px,.3vw + 16px,20px);-webkit-text-size-adjust:100%}
*{scrollbar-width:thin;scrollbar-color:#1f3a2a transparent}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:#1f3a2a;border-radius:8px}
#MainMenu,footer,header[data-testid="stHeader"],[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stToolbar"],[data-testid="stDecoration"]{display:none !important}
.stApp{background:radial-gradient(900px 520px at 50% -140px,rgba(34,197,94,.22),transparent 62%),radial-gradient(700px 420px at 105% 105%,rgba(16,185,129,.12),transparent 60%),#000;color:var(--tx)}
.stApp,.stApp p,.stApp li,.stApp label,.stApp span{color:var(--tx)}
[data-testid="stMainBlockContainer"],.block-container{max-width:100% !important;width:100%;margin:0 auto !important;padding:0 var(--pad) calc(170px + env(safe-area-inset-bottom,0px)) !important;min-height:100vh;background:rgba(4,7,5,.52);overflow-x:hidden}
@media (min-width:700px){[data-testid="stMainBlockContainer"],.block-container{max-width:760px !important;border-inline:1px solid var(--line);box-shadow:0 0 120px rgba(34,197,94,.14)}}
@media (min-width:1100px){[data-testid="stMainBlockContainer"],.block-container{max-width:940px !important}}
@media (min-width:1600px){[data-testid="stMainBlockContainer"],.block-container{max-width:1080px !important}}
[data-testid="stElementContainer"]:has(style),.element-container:has(style){display:none !important}
h1,h2,h3,h4{color:var(--tx) !important;letter-spacing:-.01em}
h4{font-size:1.3rem !important;font-weight:800 !important}
.card,.hero,.fact,.row{overflow-wrap:anywhere;min-width:0}

/* ----- hero ----- */
.hero{position:relative;overflow:hidden;contain:paint;margin:0 calc(var(--pad) * -1) 20px;padding:clamp(30px,7vw,46px) calc(var(--pad) + 6px) 28px;background:radial-gradient(120% 100% at 0% 0%,#1d8a4c 0%,#0e4026 42%,#030a06 100%);border-radius:0 0 38px 38px;border-bottom:1px solid rgba(74,222,128,.28);box-shadow:0 20px 56px rgba(34,197,94,.22);color:#fff}
.hero::before{content:"";position:absolute;right:-70px;top:-70px;width:240px;height:240px;border-radius:50%;background:radial-gradient(circle,rgba(74,222,128,.38),transparent 66%);animation:floaty 10s ease-in-out infinite alternate;will-change:transform}
.hero::after{content:"";position:absolute;left:-50px;bottom:-90px;width:220px;height:220px;border-radius:50%;background:radial-gradient(circle,rgba(16,185,129,.24),transparent 70%)}
.hero>*{position:relative;z-index:3}
.hero>.art-top{position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:1}
.hero>.scrim{position:absolute;inset:0;pointer-events:none;z-index:2;background:linear-gradient(90deg,rgba(2,10,5,.62) 0%,rgba(2,10,5,.28) 48%,transparent 80%)}
.hero .sub,.hero .loc,.hero .of{text-shadow:0 1px 8px rgba(0,0,0,.75)}
.hero .sub{font-size:.85rem;letter-spacing:.16em;text-transform:uppercase;opacity:.92;font-weight:700}
.hero .sub .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#4ade80;margin-right:10px;animation:blink 1.8s ease-in-out infinite}
.hero .title{font-size:clamp(1.95rem,6.4vw,2.8rem);font-weight:800;line-height:1.1;margin:8px 0 14px;letter-spacing:-.015em;background:linear-gradient(90deg,#fff 0%,#d9ffe6 55%,#a7f3c0 100%);-webkit-background-clip:text;background-clip:text;color:transparent !important;-webkit-text-fill-color:transparent;filter:drop-shadow(0 2px 8px rgba(0,0,0,.55))}
.hero .loc{font-size:1rem;opacity:.95;margin-bottom:10px}
.hero .big{font-size:clamp(3.4rem,12vw,5rem);font-weight:800;line-height:1;color:#4ade80;text-shadow:0 0 30px rgba(74,222,128,.55),0 2px 10px rgba(0,0,0,.6)}
.hero .of{font-size:1rem;opacity:.9;margin-left:8px}
.hero .bar{background:rgba(255,255,255,.16);margin:14px 0}
.hero .bar span{background:linear-gradient(90deg,#4ade80,#22c55e)}

/* ground band: hills + windmills + wheat. It sits BELOW all hero text (own row) so it never covers anything */
.scene{position:relative;z-index:2;aspect-ratio:600/92;margin:18px calc((var(--pad) + 6px) * -1) 0;pointer-events:none}
.scene svg{position:absolute;inset:0;width:100%;height:100%;display:block}
/* marquee strip at the very bottom of the hero */
.marq{overflow:hidden;white-space:nowrap;margin:0 calc((var(--pad) + 6px) * -1) -28px;padding:10px 0;border-top:1px solid rgba(74,222,128,.25);background:rgba(0,0,0,.45)}
.marq .track{display:inline-block;animation:marq 34s linear infinite;will-change:transform}
.marq span{display:inline-block;margin:0 20px;font-size:.88rem;font-weight:600;color:#bbf7d0}
.marq span::after{content:"✦";margin-left:40px;color:#22c55e;opacity:.7}
@keyframes marq{to{transform:translateX(-50%)}}

/* ----- animated SVG vector library (transform/opacity only) ----- */
.a-spin{animation:aspin 26s linear infinite}@keyframes aspin{to{transform:rotate(360deg)}}
.a-float{animation:afloat 6s ease-in-out infinite alternate}@keyframes afloat{from{transform:translateY(-7px)}to{transform:translateY(9px)}}
.a-drift{animation:adrift 40s ease-in-out infinite alternate}@keyframes adrift{from{transform:translateX(-45px)}to{transform:translateX(45px)}}
.a-sway{animation:asway 3.8s ease-in-out infinite alternate}@keyframes asway{from{transform:rotate(-4deg)}to{transform:rotate(5deg)}}
.a-twinkle{transform-box:fill-box;transform-origin:center;animation:atw 3s ease-in-out infinite}
@keyframes atw{0%,100%{opacity:.15}50%{opacity:1}}
.a-fall{animation:afall 13s linear infinite}
@keyframes afall{0%{transform:translate(0,-30px) rotate(0);opacity:0}10%{opacity:.8}90%{opacity:.8}100%{transform:translate(60px,250px) rotate(400deg);opacity:0}}
.a-fly{animation:afly 26s linear infinite}@keyframes afly{from{transform:translate(-90px,0)}to{transform:translate(700px,-40px)}}
.a-flap{transform-box:fill-box;transform-origin:center;animation:aflap .5s ease-in-out infinite alternate}
@keyframes aflap{from{transform:scaleY(1)}to{transform:scaleY(.3)}}
.a-ring{transform-box:fill-box;transform-origin:center;animation:aring 3.8s ease-out infinite}
@keyframes aring{0%{transform:scale(.2);opacity:.8}100%{transform:scale(1.7);opacity:0}}
.a-eq{transform-box:fill-box;transform-origin:bottom;animation:aeq 1s ease-in-out infinite alternate}
@keyframes aeq{from{transform:scaleY(.15)}to{transform:scaleY(1)}}
.a-scan{animation:ascan 3s ease-in-out infinite alternate}@keyframes ascan{from{transform:translateY(0)}to{transform:translateY(108px)}}
.a-dash{stroke-dasharray:6 8;animation:adash 1.4s linear infinite}@keyframes adash{to{stroke-dashoffset:-28}}
.a-draw{stroke-dasharray:420;stroke-dashoffset:420;animation:adraw 5s ease-in-out infinite alternate}@keyframes adraw{to{stroke-dashoffset:0}}
.a-drop{animation:adrop 1.5s linear infinite}@keyframes adrop{0%{transform:translateY(-8px);opacity:0}25%{opacity:.9}100%{transform:translateY(62px);opacity:0}}
.a-pop{transform-box:fill-box;transform-origin:center;animation:apop 3s ease-in-out infinite}
@keyframes apop{0%,100%{transform:scale(.9)}50%{transform:scale(1.15)}}
.a-hill1{animation:ahill 10s ease-in-out infinite alternate}.a-hill2{animation:ahill 13s ease-in-out infinite alternate-reverse}
@keyframes ahill{from{transform:translateX(-10px)}to{transform:translateX(10px)}}

/* ----- cards (static gradient border, animates only on hover) ----- */
.card{position:relative;overflow:hidden;background:linear-gradient(160deg,var(--s2),var(--s1));border:1px solid var(--line);border-radius:var(--r);padding:clamp(17px,3.6vw,26px);margin:0 0 16px;box-shadow:0 10px 30px rgba(0,0,0,.6),inset 0 1px 0 rgba(255,255,255,.045);color:var(--tx);font-size:1.05rem;line-height:1.55}
.card::before{content:"";position:absolute;inset:0;border-radius:inherit;padding:1.5px;background:conic-gradient(from var(--ang),transparent 0 62%,rgba(74,222,128,.9) 82%,transparent 100%);-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask:linear-gradient(#000 0 0) content-box exclude,linear-gradient(#000 0 0);mask-composite:exclude;pointer-events:none;opacity:.7}
@keyframes angle{from{--ang:210deg}to{--ang:570deg}}
.card::after{content:"";position:absolute;right:8px;top:6px;width:74px;height:74px;background:url("__CORNER__") no-repeat center/contain;opacity:.12;pointer-events:none;transform-origin:20% 90%}
.card.warn{background:linear-gradient(160deg,#241e0a,#161206);border-color:#6b560c;color:#fde68a}
.card.warn::before{background:conic-gradient(from var(--ang),transparent 0 62%,rgba(250,204,21,.9) 82%,transparent 100%)}
.card p{margin:8px 0 0}
.card ul{margin:10px 0 0;padding-left:1.25rem}
.card li{margin:8px 0;line-height:1.5}
.card .head{font-weight:800;font-size:1.2rem;line-height:1.3;position:relative;display:inline-block}
.card .head::after{content:"";display:block;height:2px;width:70%;margin-top:4px;border-radius:2px;background:linear-gradient(90deg,#4ade80,transparent);transform-origin:left;animation:underline 3.4s ease-in-out infinite alternate}
@keyframes underline{from{transform:scaleX(.3)}to{transform:scaleX(1)}}
@media (hover:hover){
.card{transition:transform .25s,border-color .25s,box-shadow .25s}
.card:hover{transform:translateY(-3px);border-color:var(--line2);box-shadow:0 16px 40px rgba(0,0,0,.65),0 0 30px rgba(34,197,94,.16)}
.card:hover::before{animation:angle 4s linear infinite}
.card:hover::after{animation:afloat 3s ease-in-out infinite alternate}}
.muted{color:var(--mut) !important;font-size:.95rem}
.method{font-size:1.4rem;font-weight:800;color:var(--g3);margin:4px 0 6px;line-height:1.25;text-shadow:0 0 18px rgba(74,222,128,.35)}
.chips{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}
.chip{background:rgba(34,197,94,.14);border:1px solid rgba(74,222,128,.22);color:#86efac;border-radius:99px;padding:6px 14px;font-size:.92rem;font-weight:600;transition:transform .2s,box-shadow .2s}
.bar{height:12px;border-radius:99px;background:#16221a;overflow:hidden}
.bar span{position:relative;overflow:hidden;display:block;height:100%;border-radius:99px;background:repeating-linear-gradient(45deg,rgba(255,255,255,.16) 0 8px,transparent 8px 16px),linear-gradient(90deg,#16a34a,#4ade80);box-shadow:0 0 14px rgba(74,222,128,.5);transform-origin:left center;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) both}
.bar span::after{content:"";position:absolute;inset:0;background:linear-gradient(100deg,transparent 30%,rgba(255,255,255,.55) 50%,transparent 70%);transform:translateX(-100%);animation:shimmer 3s ease-in-out 1.2s infinite}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes shimmer{to{transform:translateX(100%)}}
.pill{display:inline-block;padding:6px 14px;border-radius:99px;font-size:.92rem;font-weight:700}
.pill::before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;background:currentColor;margin-right:8px;animation:blink 1.6s ease-in-out infinite}
@keyframes blink{50%{opacity:.25}}
.pill.green{background:rgba(34,197,94,.20);color:#4ade80}
.pill.yellow{background:rgba(250,204,21,.18);color:#facc15}
.pill.red{background:rgba(248,113,113,.18);color:#f87171}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:12px}
.fact{background:var(--bg);border:1px solid var(--line);border-radius:16px;padding:13px 15px;position:relative;overflow:hidden;transition:transform .2s,box-shadow .2s}
.fact::after{content:"";position:absolute;inset:0;background:linear-gradient(110deg,transparent 40%,rgba(74,222,128,.14) 50%,transparent 60%);transform:translateX(-120%);pointer-events:none}
@media (hover:hover){.fact:hover::after{animation:sweep 1.1s ease}.fact:hover,.chip:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(34,197,94,.18)}}
@keyframes sweep{to{transform:translateX(120%)}}
.fact small{display:block;color:var(--mut);font-size:.88rem}
.fact b{font-size:1.15rem}
.row{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;padding:13px 0;border-bottom:1px solid var(--line);font-size:1.02rem;transition:background .2s}
.row:hover{background:linear-gradient(90deg,rgba(34,197,94,.10),transparent)}
.row:last-child{border:0}
.row .nm{font-weight:700;flex:0 0 auto;max-width:42%}
.row .rt{text-align:right;flex:1 1 0;min-width:0;color:var(--g3);font-weight:600;font-size:1rem}
.row .rt small{display:block;color:var(--mut);font-weight:500}
.srow{display:grid;grid-template-columns:minmax(0,120px) minmax(0,1fr) 46px;gap:12px;align-items:center;margin:12px 0;font-size:1rem}
.srow em{font-style:normal;color:var(--mut);text-align:right}
.soon{text-align:center;color:#4b6355;padding:60px 0;font-weight:600;animation:blink 2s infinite}
.verdict{font-size:1.5rem;font-weight:800;line-height:1.25;margin:4px 0;animation:popin .6s cubic-bezier(.2,.9,.3,1.3) both}
.verdict.ok{color:#4ade80}.verdict.bad{color:#f87171}.verdict.mid{color:#facc15}
@keyframes popin{from{opacity:0;transform:scale(.88)}to{opacity:1;transform:none}}

/* ----- buttons ----- */
.stButton>button,.stFormSubmitButton>button,.stDownloadButton>button{width:100%;border-radius:18px;min-height:58px;font-weight:700;font-size:1.05rem;transition:transform .15s,box-shadow .2s,border-color .2s}
.stButton>button p,.stFormSubmitButton>button p{font-size:1.05rem !important;font-weight:700}
.stButton>button:not([kind="primary"]),.stDownloadButton>button{background:linear-gradient(160deg,var(--s2),var(--s1));border:1.5px solid var(--line2);color:#c9f2d8}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primaryFormSubmit"],button[data-testid="stBaseButton-primary"],button[data-testid="stBaseButton-primaryFormSubmit"]{background:linear-gradient(135deg,#16a34a,#22c55e 55%,#4ade80);border:0;color:#03130a !important;box-shadow:0 8px 24px rgba(34,197,94,.34);position:relative;overflow:hidden}
.stButton>button[kind="primary"] p,.stFormSubmitButton>button p{color:#03130a !important}
.stButton>button:hover,.stFormSubmitButton>button:hover{transform:translateY(-2px);box-shadow:0 10px 28px rgba(34,197,94,.30);border-color:var(--g2)}
.stButton>button:active,.stFormSubmitButton>button:active{transform:scale(.97)}
.stButton>button[kind="primary"]::after,.stFormSubmitButton>button::after,button[data-testid="stBaseButton-primary"]::after{content:"";position:absolute;top:0;left:-70%;width:45%;height:100%;background:linear-gradient(100deg,transparent,rgba(255,255,255,.45),transparent);transform:skewX(-20deg);transition:left .6s}
.stButton>button[kind="primary"]:hover::after,.stFormSubmitButton>button:hover::after,button[data-testid="stBaseButton-primary"]:hover::after{left:130%}

/* ----- inputs ----- */
[data-testid="stWidgetLabel"] p,label[data-testid="stWidgetLabel"]{font-size:1.02rem !important;font-weight:600;color:#c9eed6 !important}
[data-baseweb="input"],[data-baseweb="base-input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{background:var(--s1) !important;border-color:var(--line2) !important;border-radius:16px !important}
.stTextInput input,.stTextArea textarea,.stNumberInput input,[data-baseweb="select"] input{background:transparent !important;color:var(--tx) !important;font-size:1.06rem !important;min-height:54px;padding:12px 16px !important;border:0 !important}
[data-baseweb="select"]>div,[data-testid="stSelectbox"] [data-baseweb="select"]>div:first-child{min-height:58px !important;font-size:1.06rem}
[data-baseweb="input"]:focus-within,[data-baseweb="textarea"]:focus-within,[data-baseweb="select"]:focus-within>div{border-color:var(--g2) !important;box-shadow:0 0 0 3px rgba(34,197,94,.22),0 0 24px rgba(34,197,94,.22) !important}
[data-baseweb="popover"] [data-baseweb="menu"],[data-baseweb="popover"]>div{background:var(--s2) !important;border:1px solid var(--line2);border-radius:16px}
[data-baseweb="popover"] li{font-size:1.04rem !important;padding:13px 16px !important}
[data-baseweb="popover"] li:hover,[data-baseweb="popover"] li[aria-selected="true"]{background:rgba(34,197,94,.16) !important}
[data-testid="stFileUploaderDropzone"]{background:var(--s1);border:2px dashed var(--line2);border-radius:20px;padding:24px;transition:border-color .25s,box-shadow .25s}
[data-testid="stFileUploaderDropzone"]:hover{border-color:#4ade80;box-shadow:0 0 28px rgba(34,197,94,.25)}
[data-testid="stCameraInput"] video,[data-testid="stCameraInput"]>div{border-radius:20px}

/* ----- tabs ----- */
[role="tablist"]{gap:10px !important;overflow-x:auto;padding:4px 2px 12px !important;scrollbar-width:none;border-bottom:0 !important}
[role="tab"]{flex:0 0 auto;height:auto !important;min-height:48px;background:var(--s2) !important;border:1px solid var(--line) !important;border-radius:999px !important;padding:10px 20px !important;color:var(--mut);transition:.2s}
[role="tab"]:hover{transform:translateY(-2px);border-color:var(--line2) !important}
[role="tab"] p{font-size:1.04rem !important;font-weight:600}
[role="tab"][aria-selected="true"]{background:linear-gradient(135deg,rgba(34,197,94,.30),rgba(34,197,94,.10)) !important;border-color:rgba(74,222,128,.55) !important;box-shadow:0 0 22px rgba(34,197,94,.32)}
[role="tab"][aria-selected="true"] p{color:var(--g3) !important}
[role="tablist"]>*:not([role="tab"]),[data-baseweb="tab-highlight"],[data-baseweb="tab-border"]{display:none !important}
[role="tab"] .react-aria-Selection,[role="tab"]>div:not([data-testid="stMarkdownContainer"]){display:none !important}
[role="tab"]::before,[role="tab"]::after,[role="tablist"]::before,[role="tablist"]::after{display:none !important;content:none !important}
[data-testid="stSelectbox"] [role="group"],[data-testid="stSelectbox"] div:has(>[role="group"]){min-height:58px !important;align-items:center;border-radius:16px !important}
[data-testid="stSelectbox"] [role="group"]{background:var(--s1) !important;border:1.5px solid var(--line2) !important;font-size:1.06rem}
[data-testid="stSelectbox"] [role="group"]:focus-within{border-color:var(--g2) !important;box-shadow:0 0 0 3px rgba(34,197,94,.22)}
[data-testid="stSelectbox"] input{font-size:1.06rem !important}
[role="tabpanel"]{animation:fadein .4s ease both}
@keyframes fadein{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}

/* ----- metrics, alerts, expanders, tables, chat ----- */
[data-testid="stMetric"]{position:relative;overflow:hidden;background:linear-gradient(160deg,var(--s2),var(--s1));border:1px solid var(--line);border-radius:20px;padding:16px 18px;box-shadow:0 8px 24px rgba(0,0,0,.5);transition:transform .25s,box-shadow .25s}
[data-testid="stMetric"]::after{content:"";position:absolute;left:0;bottom:0;height:3px;width:100%;background:linear-gradient(90deg,transparent,#4ade80,transparent);transform:translateX(-100%)}
@media (hover:hover){[data-testid="stMetric"]:hover{transform:translateY(-4px);box-shadow:0 14px 34px rgba(34,197,94,.22)}[data-testid="stMetric"]:hover::after{animation:sweep 1.2s ease}}
[data-testid="stMetricLabel"] p{font-size:.98rem !important;color:var(--mut) !important}
[data-testid="stMetricValue"]{font-size:clamp(1.7rem,6vw,2.3rem);font-weight:800;color:var(--g3);text-shadow:0 0 16px rgba(74,222,128,.35)}
[data-testid="stAlert"]{border-radius:18px;border:1px solid var(--line2);font-size:1.05rem;animation:slidein .5s cubic-bezier(.2,.8,.2,1) both}
[data-testid="stAlert"] p{font-size:1.05rem !important;line-height:1.5}
@keyframes slidein{from{opacity:0;transform:translateX(-16px)}to{opacity:1;transform:none}}
[data-testid="stExpander"]{background:linear-gradient(160deg,var(--s2),var(--s1));border:1px solid var(--line) !important;border-radius:var(--r);box-shadow:0 8px 26px rgba(0,0,0,.5);margin-bottom:16px;overflow:hidden;transition:border-color .25s,box-shadow .25s}
[data-testid="stExpander"]:hover{border-color:var(--line2) !important;box-shadow:0 10px 30px rgba(34,197,94,.14)}
[data-testid="stExpander"] summary{padding:14px 16px;font-size:1.04rem;font-weight:600}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:18px;overflow:hidden}
[data-testid="stCaptionContainer"]{color:var(--mut);font-size:.95rem}
[data-testid="stChatMessage"]{background:linear-gradient(160deg,var(--s2),var(--s1));border:1px solid var(--line);border-radius:20px;padding:14px 16px;margin-bottom:12px;animation:slidein .5s cubic-bezier(.2,.8,.2,1) both}
[data-testid="stChatMessage"] p,[data-testid="stChatMessage"] li{font-size:1.05rem;line-height:1.6;color:var(--tx)}
[data-testid="stSpinner"] p{font-size:1.02rem}
hr{border-color:var(--line) !important}

/* ----- small phones: 2 columns per row so nothing is squeezed ----- */
@media (max-width:640px){
[data-testid="stHorizontalBlock"]{flex-wrap:wrap !important;gap:.8rem !important}
[data-testid="stColumn"],[data-testid="column"]{flex:1 1 calc(50% - .8rem) !important;min-width:calc(50% - .8rem) !important;width:auto !important}}

/* ----- bottom navigation: floating bar (solid, no backdrop blur = much cheaper) ----- */
.st-key-bottom_nav{position:fixed;left:50%;bottom:calc(10px + env(safe-area-inset-bottom,0px));transform:translateX(-50%);width:min(calc(100vw - 20px),600px);box-sizing:border-box;z-index:1000;background:rgba(9,15,11,.95);border:1px solid var(--line2);border-radius:30px;box-shadow:0 16px 44px rgba(0,0,0,.75),0 0 30px rgba(34,197,94,.14);padding:8px;animation:navin .7s cubic-bezier(.2,.8,.2,1) .15s both}
@keyframes navin{from{opacity:0;transform:translateX(-50%) translateY(40px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}
.st-key-bottom_nav [role="radiogroup"]{display:flex !important;flex-wrap:nowrap !important;width:100%;gap:6px}
.st-key-bottom_nav [role="radiogroup"]>*{flex:1 1 0 !important;min-width:0 !important;margin:0 !important}
.st-key-bottom_nav [data-testid="stWidgetLabel"]{display:none !important}
.st-key-bottom_nav label{position:relative;flex:1 1 0 !important;width:100%;min-width:0 !important;justify-content:center;margin:0 !important;padding:9px 2px !important;border-radius:22px;cursor:pointer;transition:background .2s,transform .15s}
.st-key-bottom_nav label:hover{background:rgba(34,197,94,.10);transform:translateY(-2px)}
.st-key-bottom_nav label>span,.st-key-bottom_nav label>input,.st-key-bottom_nav label>div:not(:has([data-testid="stMarkdownContainer"])){display:none !important}
.st-key-bottom_nav label>div{margin:0 !important;padding:0 !important;width:100%}
.st-key-bottom_nav label p{white-space:pre-line;text-align:center;font-size:.78rem !important;line-height:1.35;color:#7f9488 !important;margin:0}
.st-key-bottom_nav label p::first-line{font-size:1.7rem}
.st-key-bottom_nav label:has(input:checked){background:linear-gradient(160deg,rgba(34,197,94,.28),rgba(34,197,94,.08));box-shadow:0 0 22px rgba(34,197,94,.3),inset 0 0 0 1px rgba(74,222,128,.45);animation:navpop .45s cubic-bezier(.2,.9,.3,1.4) both}
.st-key-bottom_nav label:has(input:checked)::after{content:"";position:absolute;left:50%;bottom:3px;width:20px;height:3px;border-radius:3px;background:var(--g3);transform:translateX(-50%);box-shadow:0 0 10px var(--g3)}
.st-key-bottom_nav label:has(input:checked) p{color:var(--g3) !important;font-weight:700}
@keyframes navpop{0%{transform:scale(.86)}60%{transform:scale(1.08)}100%{transform:scale(1)}}

/* ===== page background: every moving layer is a transform-only (GPU) animation ===== */
.stApp::before{content:"";position:fixed;inset:-10%;z-index:0;pointer-events:none;background:radial-gradient(420px 420px at 18% 22%,rgba(34,197,94,.24),transparent 70%),radial-gradient(520px 520px at 85% 70%,rgba(16,185,129,.18),transparent 70%),radial-gradient(360px 360px at 55% 105%,rgba(74,222,128,.14),transparent 70%),radial-gradient(300px 300px at 90% 10%,rgba(56,189,248,.10),transparent 70%);animation:drift 30s ease-in-out infinite alternate;will-change:transform}
@keyframes drift{from{transform:translate3d(-2%,1%,0) scale(1)}to{transform:translate3d(2%,-2%,0) scale(1.08)}}
.stApp::after{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;background-image:url("__HEX__");background-size:56px 100px;-webkit-mask-image:radial-gradient(ellipse at 50% 0%,#000 0%,transparent 72%);mask-image:radial-gradient(ellipse at 50% 0%,#000 0%,transparent 72%);opacity:.42}
[data-testid="stAppViewContainer"]{position:relative;z-index:1}
/* rising spores: one oversized layer slid by exactly one tile -> seamless loop, no repaint */
[data-testid="stAppViewContainer"]::before{content:"";position:fixed;left:0;top:0;width:100%;height:calc(100% + 340px);z-index:2;pointer-events:none;background-image:radial-gradient(circle,rgba(200,255,214,.95) 0 1.3px,transparent 2.6px),radial-gradient(circle,rgba(134,239,172,.9) 0 1.8px,transparent 3.4px),radial-gradient(circle,rgba(190,242,100,.8) 0 1.2px,transparent 2.4px);background-size:340px 340px,340px 340px,340px 340px;background-position:30px 60px,170px 220px,260px 120px;opacity:.5;animation:spores 42s linear infinite;will-change:transform}
@keyframes spores{to{transform:translate3d(0,-340px,0)}}
/* drifting leaf pattern: oversized layer slid by exactly one 200px tile */
[data-testid="stAppViewContainer"]::after{content:"";position:fixed;left:-200px;top:-200px;width:calc(100% + 200px);height:calc(100% + 200px);z-index:0;pointer-events:none;background-image:url("__LEAF__");background-size:200px 200px;opacity:.13;animation:leafdrift 90s linear infinite;will-change:transform}
@keyframes leafdrift{to{transform:translate3d(200px,200px,0)}}

/* content glides in, one block after another (plays once) */
[data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]>[data-testid="stElementContainer"]:not(.st-key-bottom_nav){animation:rise .55s cubic-bezier(.2,.8,.2,1) both}
[data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]>*:nth-child(2){animation-delay:.05s}
[data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]>*:nth-child(3){animation-delay:.10s}
[data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]>*:nth-child(4){animation-delay:.15s}
[data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]>*:nth-child(5){animation-delay:.20s}
[data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]>*:nth-child(n+6){animation-delay:.25s}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes floaty{from{transform:translate(0,0) scale(1)}to{transform:translate(-26px,22px) scale(1.2)}}

/* phones & low-power: keep the look, drop the heaviest full-screen motion */
@media (max-width:640px){
.stApp::before,[data-testid="stAppViewContainer"]::after{animation:none}
[data-testid="stAppViewContainer"]::before{animation-duration:70s}
.hero::before{animation:none}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none !important;transition:none !important}}
</style>"""

CSS = (CSS.replace("__LEAF__", LEAF_TILE).replace("__HEX__", HEX_TILE).replace("__CORNER__", CORNER_LEAF))


# ---------------------------------------------------------------- SVG scenery pieces
def _rays(cx, cy, r1=30, r2=48, n=14):
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        ro = r2 if i % 2 == 0 else r2 - 9
        out.append(f'<line x1="{cx + r1 * math.cos(a):.1f}" y1="{cy + r1 * math.sin(a):.1f}" '
                   f'x2="{cx + ro * math.cos(a):.1f}" y2="{cy + ro * math.sin(a):.1f}"/>')
    return (f'<g class="a-spin" style="transform-origin:{cx}px {cy}px" stroke="#fde68a" stroke-width="2.2" '
            f'stroke-linecap="round" opacity=".7">{"".join(out)}</g>')


def _sun(cx, cy):
    return (f'<g class="a-float" style="animation-duration:7s"><circle cx="{cx}" cy="{cy}" r="58" fill="url(#gSun)"/>'
            f'{_rays(cx, cy)}<circle cx="{cx}" cy="{cy}" r="17" fill="#ecfccb"/></g>')


def _cloud(x, y, s, dur, delay):
    return (f'<g transform="translate({x} {y}) scale({s})"><g class="a-drift" style="animation-duration:{dur}s;'
            f'animation-delay:-{delay}s"><path d="M8 34Q-2 34 0 25Q2 17 12 18Q14 6 28 8Q36-2 50 6Q64 4 66 18Q80 18 '
            f'78 28Q78 34 70 34Z" fill="#d1fae5" opacity=".15"/></g></g>')


def _stars(rng, n=14):
    return "".join(f'<circle class="a-twinkle" cx="{rng.randint(10, 590)}" cy="{rng.randint(8, 170)}" '
                   f'r="{rng.uniform(.8, 1.8):.1f}" fill="#d9ffe6" style="animation-delay:-{rng.random() * 3:.1f}s;'
                   f'animation-duration:{2.5 + rng.random() * 3:.1f}s"/>' for _ in range(n))


def _leaves(rng, n=6):
    out = []
    for i in range(n):
        x, s = 300 + i * 52 + rng.randint(-10, 10), rng.uniform(.6, 1.1)
        out.append(f'<g transform="translate({x} 0) scale({s:.2f})"><g class="a-fall" style="animation-duration:'
                   f'{rng.randint(10, 17)}s;animation-delay:-{rng.randint(0, 14)}s"><path d="M0 0c8-10 20-8 24 2-10 6-20 '
                   f'6-24-2z" fill="#4ade80" opacity=".7"/><path d="M0 0l22 2" stroke="#052e16" stroke-width=".8" '
                   f'opacity=".5"/></g></g>')
    return "".join(out)


def _birds():
    bird = ('<g class="a-flap"><path d="M0 0q6-8 12 0q6-8 12 0" stroke="#d1fae5" stroke-width="1.7" fill="none" '
            'stroke-linecap="round"/></g>')
    return "".join(f'<g transform="translate(0 {y}) scale({s})"><g class="a-fly" style="animation-duration:{d}s;'
                   f'animation-delay:-{dl}s">{bird}</g></g>' for y, s, d, dl in ((46, 1, 24, 3), (78, .75, 34, 14)))


def _rings(cx, cy):
    return "".join(f'<circle class="a-ring" cx="{cx}" cy="{cy}" r="46" fill="none" stroke="#4ade80" stroke-width="1.6" '
                   f'style="animation-delay:-{d}s"/>' for d in (0, 1.9))


def _drop(x, y, d, delay):
    return (f'<g transform="translate({x} {y})"><g class="a-drop" style="animation-duration:{d}s;animation-delay:'
            f'-{delay}s"><path d="M0-8C4-2 6 2 0 6-6 2-4-2 0-8Z" fill="#7dd3fc" opacity=".9"/></g></g>')


def _variant_field():
    arcs = "".join(f'<path class="a-dash" d="M452 162q{-30 - i * 22} {-70 - i * 12} {-84 - i * 30} {-30 - i * 4}" '
                   f'stroke="#7dd3fc" stroke-width="1.8" fill="none" stroke-linecap="round" '
                   f'style="animation-delay:-{i * .3}s"/>' for i in range(3))
    drops = "".join(_drop(300 + i * 32, 118 + (i % 3) * 8, 1.3 + (i % 4) * .25, i * .4) for i in range(5))
    return (_sun(450, 62) + arcs + drops +
            '<rect x="446" y="158" width="12" height="22" rx="3" fill="#38bdf8" opacity=".85"/>'
            '<circle cx="452" cy="156" r="6" fill="#7dd3fc" class="a-pop"/>')


def _variant_chat():
    def bubble(x, y, w, fill, delay):
        return (f'<g class="a-float" style="animation-duration:5s;animation-delay:-{delay}s"><rect x="{x}" y="{y}" '
                f'width="{w}" height="46" rx="18" fill="{fill}" opacity=".32" stroke="#86efac" stroke-opacity=".6"/>'
                f'<path d="M{x + 18} {y + 44}l-8 14 22-12z" fill="{fill}" opacity=".32"/>'
                + "".join(f'<circle class="a-twinkle" cx="{x + 24 + i * 16}" cy="{y + 23}" r="4" fill="#ecfccb" '
                          f'style="animation-delay:-{i * .4}s"/>' for i in range(3)) + '</g>')
    return _rings(400, 110) + bubble(310, 40, 110, "#22c55e", 0) + bubble(380, 120, 96, "#16a34a", 2)


def _variant_scan():
    brackets = "M326 32h-14v14M464 32h14v14M326 162h-14v-14M464 162h14v-14"
    return (_rings(395, 98) +
            '<g class="a-float" style="animation-duration:6s"><path d="M350 150C322 112 342 62 412 40c28 50 18 100-62 110z" '
            'fill="#16a34a" fill-opacity=".35" stroke="#86efac" stroke-width="2"/><path d="M350 150L404 58" stroke="#bbf7d0" '
            'stroke-width="1.6"/><path d="M372 120l22-2M382 100l20-2M392 80l16-2" stroke="#bbf7d0" stroke-width="1.2"/></g>'
            f'<path class="a-pop" d="{brackets}" stroke="#4ade80" stroke-width="3" fill="none" stroke-linecap="round"/>'
            '<g class="a-scan"><rect x="328" y="40" width="136" height="3" rx="2" fill="#4ade80"/>'
            '<rect x="328" y="30" width="136" height="12" fill="#4ade80" opacity=".18"/></g>')


def _variant_sound():
    rng = random.Random(3)
    bars = "".join(f'<rect class="a-eq" x="{310 + i * 14}" y="{170 - h}" width="8" height="{h}" rx="3" '
                   f'fill="url(#gBar)" style="animation-duration:{.6 + rng.random() * .9:.2f}s;animation-delay:-{rng.random():.2f}s"/>'
                   for i, h in enumerate(rng.randint(22, 92) for _ in range(11)))
    wave = ('<path class="a-dash" d="M290 84q15-34 30 0t30 0t30 0t30 0t30 0t30 0" stroke="#86efac" stroke-width="2" fill="none" '
            'stroke-linecap="round"/>')
    return _rings(420, 60) + wave + bars + '<circle cx="420" cy="60" r="9" fill="#bbf7d0" class="a-pop"/>'


def _variant_market():
    pts = [(300, 160), (332, 128), (362, 142), (396, 96), (430, 112), (474, 58)]
    d = "M" + " L".join(f"{x} {y}" for x, y in pts)
    dots = "".join(f'<circle class="a-pop" cx="{x}" cy="{y}" r="4.5" fill="#ecfccb" style="animation-delay:-{i * .4}s"/>'
                   for i, (x, y) in enumerate(pts))
    rain = "".join(_drop(322 + i * 18, 52, 1.2 + (i % 3) * .3, i * .25) for i in range(4))
    return ('<g class="a-float" style="animation-duration:8s"><path d="M308 46q-14 0-12-12q2-12 16-10q4-16 22-12q12-10 26 0q18-2 20 14q12 2 10 12z" '
            'fill="#bbf7d0" opacity=".28"/></g>' + rain +
            f'<path class="a-draw" d="{d}" stroke="#4ade80" stroke-width="3.2" fill="none" stroke-linecap="round" '
            f'stroke-linejoin="round"/>' + dots +
            '<g class="a-float" style="animation-duration:4s"><circle cx="486" cy="140" r="14" fill="#facc15" opacity=".85"/>'
            '<text x="486" y="145" font-size="14" font-weight="800" fill="#422006" text-anchor="middle">₹</text></g>')


def _kind(sub, title):
    s = f"{sub} {title}".lower()
    for key, name in (("ask", "chat"), ("krishi", "chat"), ("scan", "scan"), ("disease", "scan"),
                      ("eco", "sound"), ("sound", "sound"), ("live", "market"), ("market", "market")):
        if key in s:
            return name
    return "field"


def _art_top(kind):
    rng = random.Random(7)
    defs = ('<defs><radialGradient id="gSun"><stop offset="0" stop-color="#bef264" stop-opacity=".9"/>'
            '<stop offset=".55" stop-color="#4ade80" stop-opacity=".25"/><stop offset="1" stop-color="#4ade80" '
            'stop-opacity="0"/></radialGradient><linearGradient id="gBar" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0" stop-color="#bef264"/><stop offset="1" stop-color="#16a34a"/></linearGradient></defs>')
    extra = {"field": _variant_field, "chat": _variant_chat, "scan": _variant_scan,
             "sound": _variant_sound, "market": _variant_market}[kind]()
    inner = (defs + _stars(rng) + _cloud(30, 34, 1, 44, 4) + _cloud(500, 120, .7, 60, 9)
             + _birds() + _leaves(rng) + extra)
    return (f'<svg class="art-top" viewBox="0 0 600 260" preserveAspectRatio="xMidYMin slice" '
            f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">{inner}</svg>')


def _wheat_stem(x, h):
    grains = "".join(f'<ellipse cx="{x + (3 if i % 2 else -3)}" cy="{92 - h + i * 5}" rx="1.9" ry="4" '
                     f'transform="rotate({25 if i % 2 else -25} {x} {92 - h + i * 5})" fill="#facc15" opacity=".85"/>'
                     for i in range(4))
    return (f'<path d="M{x} 92Q{x + 3} {92 - h // 2} {x} {92 - h}" stroke="#4ade80" stroke-width="1.4" fill="none"/>'
            f'{grains}<ellipse cx="{x}" cy="{92 - h - 4}" rx="2" ry="5" fill="#fde047"/>')


def _windmill(cx, cy, k=1.0):
    blades = "".join(f'<path d="M{cx} {cy}L{cx - 3 * k:.1f} {cy - 24 * k:.1f}L{cx + 3 * k:.1f} {cy - 24 * k:.1f}Z" '
                     f'fill="#d1fae5" opacity=".85" transform="rotate({a} {cx} {cy})"/>' for a in (0, 120, 240))
    return (f'<path d="M{cx - 3} 92L{cx} {cy}L{cx + 3} 92Z" fill="#a7f3d0" opacity=".7"/>'
            f'<g class="a-spin" style="transform-origin:{cx}px {cy}px;animation-duration:8s">{blades}</g>'
            f'<circle cx="{cx}" cy="{cy}" r="3" fill="#4ade80"/>')


def _scene():
    """Hills + windmills + wheat. Wheat sways in THREE groups (not per stalk) to stay cheap."""
    rng = random.Random(11)
    groups = ["", "", ""]
    for i in range(24):
        groups[i % 3] += _wheat_stem(12 + i * 25 + rng.randint(-5, 5), rng.randint(16, 34))
    swaying = "".join(f'<g class="a-sway" style="transform-origin:300px 92px;animation-delay:-{j * 1.2:.1f}s">{g}</g>'
                      for j, g in enumerate(groups))
    return ('<div class="scene"><svg viewBox="0 0 600 92" preserveAspectRatio="xMidYMax slice" '
            'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
            '<path class="a-hill1" d="M-30 58Q70 30 160 50T320 42T470 54T640 46V92H-30Z" fill="#0a3a20" opacity=".85"/>'
            '<path class="a-hill2" d="M-30 70Q90 48 190 64T400 58T640 66V92H-30Z" fill="#06281a" opacity=".95"/>'
            + _windmill(96, 34, .9) + _windmill(512, 40, .8) +
            '<path d="M-30 82Q120 72 250 82T640 78V92H-30Z" fill="#031a0f"/>' + swaying + '</svg></div>')


_MARQUEE_ITEMS = ["🌾 CropShield AI", "💧 Smart irrigation", "🍃 Leaf doctor", "🔊 Eco sound", "📈 Live mandi prices",
                  "🌦️ 7-day weather", "🏛️ Govt schemes", "💬 Hindi & English"]


def _marquee():
    one = "".join(f"<span>{esc(t)}</span>" for t in _MARQUEE_ITEMS)
    return f'<div class="marq"><div class="track">{one}{one}</div></div>'


# ---------------------------------------------------------------- public helpers (same API as before)
def esc(x) -> str:
    return html.escape(str(x))


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(sub: str, title: str, body: str = ""):
    kind = _kind(sub, title)
    st.markdown(f'<div class="hero">{_art_top(kind)}<div class="scrim"></div>'
                f'<div class="sub"><i class="dot"></i>{esc(sub)}</div>'
                f'<div class="title">{esc(title)}</div>{body}{_scene()}{_marquee()}</div>', unsafe_allow_html=True)


def card(inner: str, warn: bool = False):
    st.markdown(f'<div class="card{" warn" if warn else ""}">{inner}</div>', unsafe_allow_html=True)


def pill(band: str) -> str:
    return f'<span class="pill {band.split()[0].lower()}">{esc(band)}</span>'


def meter(score: float) -> str:
    return f'<div class="bar"><span style="width:{max(0, min(100, score)):.0f}%"></span></div>'


def facts(items) -> str:
    return '<div class="grid">' + "".join(
        f'<div class="fact"><small>{esc(k)}</small><b>{esc(v)}</b></div>' for k, v in items) + "</div>"


def rows(items) -> str:
    """items: (name, main text, small text) -> wrapping two-line rows that never overflow."""
    return "".join(f'<div class="row"><span class="nm">{esc(a)}</span>'
                   f'<span class="rt">{esc(b)}<small>{esc(c)}</small></span></div>' for a, b, c in items)


def coming_soon():
    st.markdown('<div class="soon">Coming soon</div>', unsafe_allow_html=True)