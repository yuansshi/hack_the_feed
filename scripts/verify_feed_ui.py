#!/usr/bin/env python3
"""Exercise the real swipe feed, embedded model and return navigation in Chromium.

Requires agent-browser installed with Chrome. No paid APIs or social mutations.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8044')
    args=parser.parse_args()
    session=subprocess.check_output(['agent-browser','session','id','--scope','worktree','--prefix','feed-ui-check'],cwd=BASE,text=True).strip()
    def run(*command):
        return subprocess.check_output(['agent-browser','--session',session,*command],cwd=BASE,text=True,stderr=subprocess.PIPE).strip()
    def evaluate(expression):
        result=json.loads(run('eval','--json',expression))
        if not result['success']:raise AssertionError(result['error'])
        return result['data']['result']
    def wait(expression):run('wait','--fn',expression)
    store=BASE/'data/social_store.json'
    baseline=hashlib.sha256(store.read_bytes()).hexdigest()
    try:
        run('open',args.base_url+'/?zip=94404')
        run('set','viewport','1440','1000')
        wait('document.querySelectorAll(".source-house-card").length === 6 && document.getElementById("flip-source-photo").naturalWidth > 0')
        assert evaluate('document.querySelectorAll(".source-house-card video").length')==0
        assert evaluate('document.getElementById("flip-main-video").getAttribute("src")') is None
        # Observe all parent fetches before actions; an accidental demo/social path fails below.
        evaluate('window.feedCheckRequests=[];window.originalCheckFetch=window.fetch;window.fetch=(url,...args)=>{window.feedCheckRequests.push(String(url));return window.originalCheckFetch(url,...args);};true')
        run('click','#btn-open-available-3d')
        wait('document.getElementById("source-research-frame").contentDocument?.getElementById("canvas-wrap")?.dataset.modelState === "ready"')
        assert evaluate('document.getElementById("source-research-dialog").open') is True
        assert evaluate('document.getElementById("flip-hook-title").textContent')=='140 Spinnaker St'
        assert evaluate('document.getElementById("source-research-frame").contentDocument.querySelector("[role=tab][aria-selected=true]").dataset.view')=='model'
        photo_before=evaluate('document.getElementById("flip-source-photo").getAttribute("src")')
        run('press','d')
        assert evaluate('document.getElementById("flip-hook-title").textContent')=='140 Spinnaker St'
        # Navigate inside the real iframe using visible controls, then Escape back.
        run('frame','#source-research-frame')
        run('find','role','button','click','--name','Guided walk')
        run('frame','main')
        wait('document.getElementById("source-research-frame").contentDocument?.getElementById("canvas-wrap")?.dataset.guideState === "complete"')
        run('press','Escape')
        wait('!document.getElementById("source-research-dialog").open')
        assert evaluate('document.getElementById("source-research-frame").getAttribute("src")')=='about:blank'
        assert evaluate('document.getElementById("flip-source-photo").getAttribute("src")')==photo_before
        assert evaluate('document.activeElement.id')=='btn-open-available-3d'
        # Source save stays in the feed and never creates invented social proof.
        run('click','#btn-flip-save-up')
        wait('document.getElementById("saved-count-badge").textContent === "1" && document.getElementById("flip-hook-title").textContent === "608 Port Dr"')
        run('click','#btn-filter-saved')
        wait('document.querySelectorAll(".source-house-card").length === 1')
        assert evaluate('document.getElementById("flip-hook-title").textContent')=='140 Spinnaker St'
        # Empty results may not open a stale property through a global header action.
        run('fill','#zip-search-input','no-such-home')
        wait('document.querySelectorAll(".feed-house-card").length === 0')
        run('click','#btn-top-openhouse')
        assert evaluate('document.getElementById("source-research-dialog").open') is False
        run('fill','#zip-search-input','')
        run('click','[data-zip="94301"]')
        wait('document.querySelectorAll(".feed-card-video").length > 0')
        assert evaluate('document.getElementById("flip-video-scrubber").disabled') is False
        run('click','[data-zip="94404"]')
        wait('document.querySelectorAll(".source-house-card").length === 6')
        assert evaluate('document.getElementById("flip-main-video").getAttribute("src")') is None
        requests=evaluate('window.feedCheckRequests')
        assert not any('/api/gemini/' in url or '/api/gmi/' in url or '/api/oriane/' in url or '/api/social/' in url for url in requests),requests
        run('set','viewport','390','844')
        assert evaluate('document.documentElement.scrollWidth <= innerWidth') is True
        scroll_before=evaluate('document.querySelector(".front-showcase-layout").scrollTop')
        run('click','#btn-open-available-3d')
        wait('document.getElementById("source-research-frame").contentDocument?.getElementById("canvas-wrap")?.dataset.modelState === "ready"')
        assert evaluate('(()=>{const f=document.getElementById("source-research-frame"),r=f.contentDocument.getElementById("guide").getBoundingClientRect();return r.top>=0 && r.bottom < f.clientHeight;})()') is True
        run('click','#research-back')
        assert evaluate('document.querySelector(".front-showcase-layout").scrollTop')==scroll_before
        errors=json.loads(run('errors','--json'))['data']['errors']
        assert errors==[],errors
        assert hashlib.sha256(store.read_bytes()).hexdigest()==baseline
        print(json.dumps({'feed':'pass','direct_3d_overlay':'pass','guided_walk':'pass','escape_return_and_state':'pass','source_saves':'pass','empty_filter':'pass','demo_switch':'pass','mobile':'pass','paid_or_social_requests':0,'page_errors':0}))
    finally:
        run('close')

if __name__=='__main__':main()
