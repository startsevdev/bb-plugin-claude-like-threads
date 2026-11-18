#!/usr/bin/env python3
"""Build the "Thread list by day" bb plugin from bb's bundled thread-list plugin.

Copies the bundled plugin out of the installed bb.app, renames it, and patches
the frontend bundle so the chronological "Threads" section shows day headers
(Today / Yesterday / Sep 30) like Claude Desktop. Re-run after every bb update:

    python3 build.py && bb plugin reload thread-list-by-day

Every patch asserts its anchor exists exactly once, so a bb update that changes
the bundle fails loudly here instead of breaking the sidebar.
"""
import json
import re
import shutil
import sys
from pathlib import Path

SRC = Path("/Applications/bb.app/Contents/Resources/app.asar.unpacked/node_modules/"
           "bb-app/server/dist/builtin-plugins/thread-list")
OUT = Path(__file__).resolve().parent / "plugin"
OLD_ID = "thread-list"
NEW_ID = "thread-list-by-day"

# Day-group helpers, injected at the top of app.js. Placeholders in caps are
# the bundle's minified React/jsx names, resolved at patch time.
HELPERS = r"""
typeof document<"u"&&!document.getElementById("bb-thread-list-by-day-style")&&document.head.appendChild(Object.assign(document.createElement("style"),{id:"bb-thread-list-by-day-style",textContent:"[data-bb-plugin=thread-list-by-day] .bb-thread-title .whitespace-pre{white-space:nowrap!important}"}));
const __BB_DAYS=7,__BB_DAY_CAP=6,__BB_OLDER_STEP=20,__BB_COLLAPSED_KEY="bb-thread-list-by-day:collapsed";
function __bbDayKey(t){let d=new Date(t);return d.getFullYear()*10000+d.getMonth()*100+d.getDate()}
function __bbThreadOf(x){return x.kind==="thread"?x.node.thread:x.kind==="environment"?x.group.nodes[0]?.thread:null}
function __bbTime(th,sort){return sort==="created"?th.createdAt:th.status==="active"?Date.now():th.latestAttentionAt}
function __bbItemTime(x,sort){let th=__bbThreadOf(x);return th?__bbTime(th,sort):null}
function __bbGroupOf(t,now){let start=new Date(now.getFullYear(),now.getMonth(),now.getDate()-(__BB_DAYS-1)).getTime();if(t==null||t<start)return{key:"older",label:"Older"};let k=__bbDayKey(t);if(k===__bbDayKey(now.getTime()))return{key:"today",label:"Today"};if(k===__bbDayKey(new Date(now.getFullYear(),now.getMonth(),now.getDate()-1).getTime()))return{key:"yesterday",label:"Yesterday"};let d=new Date(t),o={month:"short",day:"numeric"};d.getFullYear()!==now.getFullYear()&&(o.year="numeric");return{key:"d"+k,label:d.toLocaleDateString("en-US",o)}}
let __bbCol=(()=>{try{return new Set(JSON.parse(localStorage.getItem(__BB_COLLAPSED_KEY)||"[]"))}catch{return new Set}})();const __bbColSubs=new Set;
function __bbColSub(f){__bbColSubs.add(f);return()=>{__bbColSubs.delete(f)}}
function __bbColGet(){return __bbCol}
function __bbToggle(k){let n=new Set(__bbCol);n.has(k)?n.delete(k):n.add(k);__bbCol=n;try{localStorage.setItem(__BB_COLLAPSED_KEY,JSON.stringify([...n]))}catch{}__bbColSubs.forEach(f=>f())}
function __bbGroup(items,sort,exp,sel,col){if(sort==="alpha"||items.length===0)return null;let now=new Date(),groups=new Map;for(let it of items){let g0=__bbGroupOf(__bbItemTime(it,sort),now),g=groups.get(g0.key);g||(g={...g0,items:[]},groups.set(g0.key,g));g.items.push(it)}let vis=[],info=[],first=!0;for(let g of groups.values()){let header=first?null:{key:g.key,label:g.label};first=!1;if(col.has(g.key)){vis.push(g.items[0]);info.push({header,collapsed:!0,hideRow:!0});continue}let cap=g.key==="today"||g.key==="yesterday"?1/0:(g.key==="older"?__BB_OLDER_STEP:__BB_DAY_CAP)+(exp[g.key]||0),shown=g.items.filter((it,i)=>i<cap||__bbThreadOf(it)?.id===sel),hidden=g.items.length-shown.length;shown.forEach((it,i)=>{let inf={};i===0&&(inf.header=header);i===shown.length-1&&hidden>0&&(inf.more={key:g.key,count:g.key==="older"?Math.min(hidden,__BB_OLDER_STEP):hidden});vis.push(it);info.push(inf)})}return{items:vis,info}}
function __bbFirstGroup(threads,sort,dir){if(sort==="alpha"||!threads||threads.length===0)return null;let ts=threads.map(th=>__bbTime(th,sort)),t=dir==="ascending"?Math.min(...ts):Math.max(...ts);return __bbGroupOf(t,new Date())}
function __BBFirstLabel({group}){return __JSX__("span",{className:"min-w-0 truncate",children:group?group.label:"Threads"})}
function __bbWrap(inf,row,setExp){if(!inf||(!inf.header&&!inf.more&&!inf.hideRow))return row;return __JSXS__("div",{children:[inf.header?__JSX__("div",{"data-bb-day-header":inf.header.label,style:{marginTop:14,marginBottom:inf.collapsed?0:4},children:__JSX__(__SECTION__,{label:inf.header.label,stickyHeader:!1,collapseControl:{isCollapsed:!!inf.collapsed,onToggleCollapsed:()=>__bbToggle(inf.header.key)},children:null})}):null,inf.hideRow?null:row,inf.more?__JSX__("button",{type:"button","data-bb-show-more":"",className:"flex h-7 w-full items-center text-xs text-subtle-foreground/75 select-none",style:{paddingLeft:30,cursor:"pointer",background:"none",border:0},onClick:e=>{e.stopPropagation();let m=inf.more;setExp(p=>({...p,[m.key]:(p[m.key]||0)+m.count}))},children:`Show ${inf.more.count} more`}):null]})}
"""


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed ({what}): anchor found {n} times, expected 1:\n  {old[:160]}")
    return src.replace(old, new)


def find_one(pattern: str, src: str, what: str) -> re.Match:
    matches = list(re.finditer(pattern, src))
    if len(matches) != 1:
        sys.exit(f"patch failed ({what}): pattern matched {len(matches)} times, expected 1")
    return matches[0]


def patch_app_js(js: str) -> str:
    # Resolve minified names that change between bb builds.
    sort_atom = find_one(r'[,;](\w+)=\w+\("chronologicalSort"\)', js, "sort atom").group(1)
    dir_atom = find_one(r'[,;](\w+)=\w+\("sortDirection"\)', js, "dir atom").group(1)
    mode_atom = find_one(r'[,;](\w+)=\w+\("organizationMode"\)', js, "mode atom").group(1)
    use_atom = find_one(r'h=\w+\(\),g=\w+\(\),b=(\w+)\(\w+\),y=_\(\(\)=>r\?\?', js, "atom hook").group(1)
    m = find_one(r'return (\w+)\((\w+),\{children:(\w+)\(Mr,\{ref:r', js, "jsx/fragment")
    jsx, jsxs = m.group(1), m.group(3)
    react = {k: find_one(rf'{k}:\(\)=>(\w+)', js, k).group(1)
             for k in ["useState", "useMemo", "useSyncExternalStore"]}

    # 1. The root item list (dI) groups its items by day when opted in.
    m = find_one(r'function (\w+)\(\{items:e,sectionDnd:t,variant:n,projectId:r,depthOffset:o=0,', js, "list fn")
    list_fn = m.group(1)
    js = replace_once(js, m.group(0),
                      m.group(0).replace("({items:e,", "({bbDateHeaders:__bbdh,items:e,"), "list signature")
    js = replace_once(
        js, "onRemoveSection:m}){let{itemKeys:h,",
        "onRemoveSection:m}){"
        f"let __bbsort={use_atom}({sort_atom}),[__bbx,__bbsx]={react['useState']}({{}}),"
        f"__bbcol={react['useSyncExternalStore']}(__bbColSub,__bbColGet),"
        f"__bbg={react['useMemo']}(()=>__bbdh?__bbGroup(e,__bbsort,__bbx,a,__bbcol):null,[__bbdh,e,__bbsort,__bbx,a,__bbcol]);"
                "__bbg&&(e=__bbg.items);"
        "let{itemKeys:h,", "list hook")

    # 2. Day header above the first row of each group, "Show N more" below the last.
    m = find_one(r'renderItem:S=>\{let x=e\[S\];if\(!x\)return null;let I=(\w+)\(x\);return l\((\w+),\{children:l\((\w+),\{', js, "renderItem")
    js = replace_once(js, m.group(0),
                      m.group(0).replace(f"let I={m.group(1)}(x);", f"let I={m.group(1)}(x),__h=__bbg?__bbg.info[S]:null;")
                      .replace(f"{{children:l({m.group(3)},{{", f"{{children:__bbWrap(__h,l({m.group(3)},{{"),
                      "renderItem open")
    js = replace_once(js, "sectionDnd:t??void 0})},I)}});",
                      "sectionDnd:t??void 0}),__bbsx)},I)}});", "renderItem close")

    # 3. Turn grouping on only for the chronological "Threads" root list.
    js = replace_once(js, f'=F=>l({list_fn},{{items:F,sectionDnd:E,variant:"section",',
                      f'=F=>l({list_fn},{{bbDateHeaders:!0,items:F,sectionDnd:E,variant:"section",', "enable flag")

    # 4. In Custom mode the "Threads" header shows the first group ("Today") and
    #    is not sticky, like Claude Desktop. The label editor slot swaps the text;
    #    keep the section draggable anyway.
    m = find_one(r'function (\w+)\(\{actions:e,actionsOpen:t,activity:n,collapsedThreads:r,consumeClickSuppression:o,content:i,disabled:a,id:s,isCollapsed:c,label:d,onToggleCollapsed:u\}\)\{return l\((\w+),\{id:s,label:d,stickyHeader:s!=="pinned",', js, "section header")
    js = replace_once(js, m.group(0),
                      m.group(0).replace("{return l(",
                                         f'{{let __bbmode={use_atom}({mode_atom}),__bbs={use_atom}({sort_atom}),__bbd={use_atom}({dir_atom}),__bbcol={react["useSyncExternalStore"]}(__bbColSub,__bbColGet),__bbm=s==="threads"&&__bbmode==="chronological",__bbfg=__bbm?__bbFirstGroup(r,__bbs,__bbd):null;return l(')
                      .replace('label:d,stickyHeader:s!=="pinned",',
                               'label:d,labelEditor:__bbm?l(__BBFirstLabel,{group:__bbfg}):void 0,__bbKeepDrag:__bbm,stickyHeader:s!=="pinned"&&!__bbm,'),
                      "section header")
    js = replace_once(js, "collapseControl:{isCollapsed:c,onToggleCollapsed:()=>u(s)},",
                      "collapseControl:__bbfg?{isCollapsed:__bbcol.has(__bbfg.key),__bbKeep:!0,onToggleCollapsed:()=>__bbToggle(__bbfg.key)}:{isCollapsed:c,onToggleCollapsed:()=>u(s)},",
                      "first group collapse")
    # Ia hides the chevron and trailing actions while a label editor is shown;
    # our "Today" label uses that slot, so keep them for it.
    m = find_one(r'function \w+\(\{label:e,labelEditor:t,onRename:n,children:r,[\s\S]*?function Ra\(', js, "section body")
    body = m.group(0)
    if body.count('t&&"hidden"') != 2 or body.count("disabled:!!t,") != 1:
        sys.exit("patch failed (section body): unexpected label editor checks")
    body = body.replace('t&&"hidden"', 't&&!f?.__bbKeep&&"hidden"').replace("disabled:!!t,", "disabled:!!t&&!f?.__bbKeep,")
    js = js.replace(m.group(0), body)
    js = replace_once(js, "f?.isCollapsed||r==null?null:",
                      "f?.isCollapsed&&!f.__bbKeep||r==null?null:", "keep content")
    js = replace_once(js, "dragBindings:r.labelEditor?void 0:o,",
                      "dragBindings:r.labelEditor&&!r.__bbKeepDrag?void 0:o,", "keep drag")

    # 5. Own plugin id (CSS scoping attribute, slot id) and title.
    js = js.replace(f'"{OLD_ID}"', f'"{NEW_ID}"')
    js = replace_once(js, 'title:"Thread list",', 'title:"Claude-Like Threads",', "slot title")

    section_fn = find_one(r'function (\w+)\(\{label:e,labelEditor:t,onRename:n,children:r,', js, "section fn").group(1)
    helpers = (HELPERS.replace("__SECTION__", section_fn).replace("__JSXS__", jsxs).replace("__JSX__", jsx)
               )
    return helpers.strip() + "\n" + js


def main() -> None:
    if not SRC.exists():
        sys.exit(f"bundled thread-list not found at {SRC}")
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "dist").mkdir(parents=True)

    for name in ["server.js", "package.json"]:
        shutil.copy(SRC / "dist" / name, OUT / "dist" / name)

    app_js = (SRC / "dist" / "app.js").read_text()
    (OUT / "dist" / "app.js").write_text(patch_app_js(app_js))

    css = (SRC / "dist" / "app.css").read_text()
    css = css.replace(f"data-bb-plugin={OLD_ID}]", f"data-bb-plugin={NEW_ID}]")
    (OUT / "dist" / "app.css").write_text(css)

    for meta in ["app.meta.json", "server.meta.json"]:
        data = json.loads((SRC / "dist" / meta).read_text())
        data["pluginId"] = NEW_ID
        (OUT / "dist" / meta).write_text(json.dumps(data, indent=2) + "\n")

    pkg = json.loads((SRC / "package.json").read_text())
    pkg_out = {
        "name": f"bb-plugin-{NEW_ID}",
        "version": pkg["version"],
        "engines": pkg["engines"],
        "bb": {
            "name": "Claude-Like Threads",
            "description": "bb's thread list with Today / Yesterday / date headers in the Threads section.",
            "branding": pkg["bb"].get("branding", {}),
            "server": "./dist/server.js",
            "app": "./dist/app.js",
        },
        "private": True,
        "type": "module",
        "description": "bb's thread list with day headers.",
        "keywords": ["bb-plugin"],
    }
    (OUT / "package.json").write_text(json.dumps(pkg_out, indent=2) + "\n")
    print(f"built {OUT}")


if __name__ == "__main__":
    main()
