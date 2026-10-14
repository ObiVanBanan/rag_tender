/* Run with: node tests/demo_ui_browser_smoke.cjs
   Tiny DOM harness exercises the real inline UI JS without network/browsers. */
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"../src/nomenclature_matcher/business_demo.html"),"utf8");
const script=source.match(/<script>([\s\S]*?)<\/script>/);
assert(script,"Embedded application script");
class Node {
  constructor(tag="div"){
    this.tagName=tag;this.children=[];this.parentElement=null;this.attributes={};
    this._text="";this.className="";this.id="";this.style={};this.dataset={};
    this.listeners={};this.hidden=false;this.value="";this.disabled=false;this.inert=false;
    this.classList={
      contains:name=>this.className.split(/\s+/).includes(name),
      add:name=>{if(!this.classList.contains(name))this.className=(this.className+" "+name).trim();},
      remove:name=>{this.className=this.className.split(/\s+/).filter(x=>x!==name).join(" ");},
      toggle:name=>{if(this.classList.contains(name)){this.classList.remove(name);return false;}
                     this.classList.add(name);return true;}
    };
  }
  set textContent(v){this._text=String(v??"");this.children=[];}
  get textContent(){return this._text+this.children.map(x=>x.textContent||"").join("");}
  append(...nodes){for(const item of nodes){if(item==null)continue;const n=typeof item==="string"?new Node("#text"):item;
    if(typeof item==="string")n.textContent=item;
    n.parentElement=this;this.children.push(n);}}
  replaceChildren(...nodes){this.children=[];this._text="";this.append(...nodes);}
  replaceWith(node){const parent=this.parentElement;
    if(!parent)throw Error("node without parent");
    const i=parent.children.indexOf(this);assert(i>=0);parent.children[i]=node;node.parentElement=parent;}
  get firstChild(){return this.children[0]||null;}
  setAttribute(key,value){this.attributes[key]=String(value);if(key==="id")this.id=String(value);}
  getAttribute(key){return this.attributes[key];}
  removeAttribute(key){delete this.attributes[key];}
  addEventListener(name,fn){(this.listeners[name]||=[]).push(fn);}
  click(){return Promise.all((this.listeners.click||[]).map(fn=>fn({target:this}))); }
  focus(){document.activeElement=this;}
  scrollIntoView(){}
  querySelector(q){return traverse(this,x=>q[0]==="#"?x.id===q.slice(1):q[0]==="."?
     x.className.split(/\s+/).includes(q.slice(1)):x.tagName===q);}
}
function traverse(root,fn){
 if(fn(root))return root;
 for(const child of root.children||[]){const match=traverse(child,fn);if(match)return match;}
 return null;
}
const ids=new Map();
for(const id of [
 "query","input-count","error","results","results-summary","results-section",
 "go","upload","file","clear-input","history-open","history-close",
 "history-shade","history-pane","history-list","history-count","history-clear",
 "history-save-note","tray-count","tray-approved"
]){const n=new Node("div");n.id=id;ids.set(id,n);}
const document={
 body:new Node("body"),activeElement:null,
 createElement:tag=>new Node(tag),
 createElementNS:(ns,tag)=>new Node(tag),
 createTextNode:text=>{const n=new Node("#text");n.textContent=text;return n;},
 getElementById:id=>ids.get(id)||traverse(ids.get("results"),node=>node.id===id),
 querySelectorAll:()=>[],
 addEventListener:()=>{}
};
const store=new Map();
const localStorage={
 getItem:key=>store.get(key)||null,
 setItem:(key,value)=>store.set(key,String(value)),
 removeItem:key=>store.delete(key)
};
const sampleCandidate=(id,primary=false)=>({
 ld_id:id,article:"LD-"+id,name:"Кран LD "+id,dn:80,pn:"1,6",
 selection:primary?"RECOMMENDED":"FOR_REVIEW",
 review_gate:"CHECKS_PASSED",review_note:"Совпадает DN",
 comparison:{rows:[{key:"dn",label:"Диаметр",required:"DN80",catalog:"DN80",
                     status:"MATCH",strict:true}]}
});
const risky=sampleCandidate(8002);
risky.review_gate="BLOCKED";
risky.review_note="Не соответствует: Номинальный диаметр";
const responsePayload={
 request_id:"test-session-12345678",review_token:"X".repeat(44),
 results:[{
   input:"Кран шаровый LD Ду80 Ру16 для воды",status:"MATCHED",
   message:"Техническая проверка выполнена",
   editable_constraints:{product_type:"ball_valve",dn:80,pn_min_mpa:1.6},
   parameters:[{label:"Диаметр",value:"DN80"}],missing_fields:[],
   recommended:[sampleCandidate(8000,true)],
   other_candidates:[sampleCandidate(8001),risky],
   candidates:[sampleCandidate(8000,true),sampleCandidate(8001),risky]
 }]
};
let requests=[];
const fetch=async (url,options)=>{
 requests.push({url,body:options&&options.body});
 if(url==="/v1/demo/match")return {ok:true,json:async()=>responsePayload};
 if(url==="/v1/demo/decision"){
   const body=JSON.parse(options.body);
   assert.equal(body.action,"SELECTED_OTHER");
   assert([8001,8002].includes(body.selected_ld_id));
   if(body.selected_ld_id===8002 && !body.acknowledge_mismatch)
     return {ok:false,status:409,json:async()=>({detail:"Есть расхождение с обязательными характеристиками: Номинальный диаметр"})};
   return {ok:true,json:async()=>({revision:body.revision+1,decision:"SELECTED_OTHER",
      selected_ld_id:body.selected_ld_id,manual_mismatch:!!body.acknowledge_mismatch})};
 }
 throw Error("Unexpected network call "+url);
};
const window={confirm:()=>true,scrollTo:()=>{}};
const context=vm.createContext({document,localStorage,window,fetch,console,alert:()=>{},
                                setTimeout,Date,Math,Intl,JSON,Promise,TextDecoder});
vm.runInContext(script[1],context,{filename:"business_demo.inline.js"});
async function run(){
 ids.get("query").value="Кран шаровый LD Ду80 Ру16 для воды";
 await vm.runInContext("run()",context);
 const key="ld-tender-demo-snapshots-v3";
 assert(store.has(key),"full snapshot saved");
 let snapshots=JSON.parse(store.get(key));
 assert.equal(snapshots[0].products.length,1);
 assert.equal(snapshots[0].results[0].recommended[0].article,"LD-8000");
 assert.equal(snapshots[0].results[0].candidates.length,3);
 assert(!store.get(key).includes("review_token"),"No review capability in history");
 const results=ids.get("results");
 const button=traverse(results,n=>n.tagName==="button"&&n.textContent==="Выбрать этот LD");
 assert(button,"top-10 alternative select button visible");
 await button.click();
 assert.equal(vm.runInContext("rowStates[0].decision",context),"SELECTED_OTHER");
 assert.equal(vm.runInContext("rowStates[0].selected_ld_id",context),8001);
 snapshots=JSON.parse(store.get(key));
 assert.equal(snapshots[0].rowStates[0].selected_ld_id,8001);
 assert.equal(snapshots[0].rowStates[0].decision,"SELECTED_OTHER");
 assert.equal(snapshots[0].results[0].recommended[0].article,"LD-8000",
   "Original model recommendation kept alongside user choice");
 const forced=traverse(ids.get("results"),n=>n.tagName==="button"&&n.textContent==="Выбрать вручную");
 assert(forced,"Manual selection remains accessible for a visibly mismatching candidate");
 await forced.click();
 assert.equal(vm.runInContext("rowStates[0].selected_ld_id",context),8002);
 assert.equal(vm.runInContext("rowStates[0].manual_mismatch",context),true);
 snapshots=JSON.parse(store.get(key));
 assert.equal(snapshots[0].rowStates[0].selected_ld_id,8002);
 assert.equal(snapshots[0].rowStates[0].manual_mismatch,true);
 assert(requests.some(x=>x.body&&x.body.includes('"acknowledge_mismatch":true')),
   "Mismatch exception explicitly confirmed and submitted");
 vm.runInContext("renderHistory()",context);
 const item=traverse(ids.get("history-list"),n=>n.tagName==="button"&&n.className==="history-item");
 assert(item,"history entry exists");
 const countBefore=requests.length;
 await item.click();
 assert.equal(requests.length,countBefore,"Restore doesn't call LLM or backend");
 assert.equal(vm.runInContext("activeReview",context),null,"Historical snapshots read-only");
 assert.equal(vm.runInContext("rowStates[0].selected_ld_id",context),8002);
 assert.equal(vm.runInContext("rowStates[0].manual_mismatch",context),true);
 assert.equal(vm.runInContext("liveResults[0].candidates.length",context),3);
 assert(ids.get("results").textContent.includes("LD-8002"),"Manual override restored");
 assert(ids.get("results-summary").textContent.includes("Сохранённый слепок"));
 // The user's seven-line batch must persist seven distinct answers, not merely
 // the first query string nor an aggregate count.
 responsePayload.results=Array.from({length:7},(_,i)=>({
   ...responsePayload.results[0],input:"Спецификация, позиция "+(i+1)
 }));
 ids.get("query").value=responsePayload.results.map(x=>x.input).join("\n");
 await vm.runInContext("run()",context);
 const afterSeven=JSON.parse(store.get(key));
 assert.equal(afterSeven[0].products.length,7);
 assert.equal(afterSeven[0].results.length,7);
 assert(afterSeven[0].results.every(x=>x.recommended[0].article==="LD-8000"));
 assert(!store.get(key).includes("review_token"));
 vm.runInContext("renderHistory()",context);
 const latest=traverse(ids.get("history-list"),n=>n.tagName==="button"&&n.className==="history-item");
 await latest.click();
 assert.equal(vm.runInContext("liveResults.length",context),7);
 assert.equal(vm.runInContext("activeReview",context),null);
 console.log("DOM smoke passed: top10 choice -> persisted snapshot -> offline restore; 7 of 7 items preserved.");
}
run().catch(e=>{console.error(e);process.exitCode=1;});
