/* Authenticated-user navigation policy for pinned Jellyfin Web 12.0.
 * No playback interception, API monkey-patching, credentials or item deletion.
 * Unrecognised routes/menus fail open to Jellyfin's normal UI.
 */
(() => {
    'use strict';
    const validUser=user=>typeof user==='string'&&/^[0-9a-f]{32}$/i.test(user);
    const LIBRARIES={
        '8bc59dd4449848da1641f0bd0eba752c':'Movie',
        '0831c82fb6eb808d10d974919cceaf36':'Series'
    };
    function scope(hash,user) {
        if(!validUser(user))return null;
        const [path,query='']=hash.replace(/^#/, '').split('?');
        const params=new URLSearchParams(query);
        if(path==='/livetv')return {kind:'live',params};
        const id=params.get('topParentId');
        if((path==='/movies'||path==='/tv')&&LIBRARIES[id])return {kind:LIBRARIES[id],id,params};
        return null;
    }
    function hiddenLabels(kind,ready) {
        if(kind==='live')return ['Guide','Recordings','Schedule','Series'];
        return ['Suggestions','Collections','Upcoming','Networks','Studios','Playlists',...(kind==='Series'?['Episodes']:[]),...(ready?[]:['Genres'])];
    }
    function favouritesUrl(kind,serverId) {
        return '#/list?'+new URLSearchParams({type:kind,IsFavorite:'true',tag:'Venom TV',serverId});
    }
    function categoryUrl(genreId,parentId,kind,serverId) {
        return '#/list?'+new URLSearchParams({genreId,parentId,type:kind,serverId});
    }
    function channelDisplayName(value) {
        // Display only. Do not alter API metadata, item IDs, or provider URLs.
        let label=value.replace(/\s+/g,' ').trim();
        label=label.replace(/^\d{3,6}\s+(?=(?:VIP\b|CA\b|UK\b|US\b|AR\b|NW\b))/i,'');
        label=label.replace(/^(?:(?:VIP|CA|UK|US|AR|NW)\b[\s:|.-]*)+/i,'').trim();
        return label||value;
    }
    function channelCardName(value, itemName) {
        // Use the same card's unnumbered accessible item name as evidence.
        // Never strip arbitrary digits: 24 News / 360 Arabic are real names.
        const label=value.replace(/\s+/g,' ').trim();
        const name=(itemName||'').replace(/\s+/g,' ').trim();
        if(name&&label.endsWith(' '+name)&&/^\d+(?:\.\d+)?$/.test(label.slice(0,-name.length).trim()))return channelDisplayName(name);
        return channelDisplayName(value);
    }
    globalThis.VenomNavigationPolicy={scope,hiddenLabels,favouritesUrl,categoryUrl,channelDisplayName,channelCardName};
    if(typeof document==='undefined')return;
    function pageSizePolicy(uid) {
        if(!validUser(uid))return;
        const marker=uid+'-venom-page-policy-v1';
        if(!localStorage.getItem(marker)) {
            const key=uid+'-libraryPageSize';
            localStorage.setItem(marker,JSON.stringify({previous:localStorage.getItem(key)}));
            localStorage.setItem(key,'50');
        }
    }
    // Seed a returning user's local preference before Jellyfin mounts its UI.
    // Tokens are neither used nor logged; only the scoped user ID is read.
    try{for(const s of JSON.parse(localStorage.getItem('jellyfin_credentials')||'{}').Servers||[])pageSizePolicy(s.UserId);}catch{}
    const cache=new Map();let scheduled=false;let activeUser=null;
    const style=document.createElement('style');
    style.textContent='.venomNavHidden{display:none!important}.venomIndexNotice{padding:12px 24px;opacity:.75;font-size:.9rem}.venomBrowseLinks{display:flex;gap:12px;flex-wrap:wrap;padding:12px 24px}.venomBrowseLinks a{color:inherit;text-decoration:none;border:1px solid #8886;border-radius:20px;padding:8px 16px}.venomBrowseLinks a:hover,.venomBrowseLinks a:focus-visible{background:#8884}';
    style.textContent+='.venomCategoryDialog{color:inherit;background:#181818;border:1px solid #666;border-radius:12px;width:min(900px,90vw);max-height:80vh;padding:20px}.venomCategoryDialog::backdrop{background:#000a}.venomCategoryGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.venomCategoryGrid a{color:inherit;text-decoration:none;background:#ffffff0d;border:1px solid #8886;border-radius:8px;padding:16px;min-height:50px}.venomCategoryGrid a:hover,.venomCategoryGrid a:focus-visible{background:#ffffff22}.venomCategoryGrid small{display:block;opacity:.7;margin-top:8px}.venomCategoryDialog button{padding:8px 16px;margin-bottom:16px}';
    document.head.append(style);
    function openCategories(current,client) {
        document.querySelector('.venomCategoryDialog')?.remove();
        const dialog=document.createElement('dialog');dialog.className='venomCategoryDialog';dialog.setAttribute('aria-label','Venom provider categories');
        const title=document.createElement('h2');title.textContent=current.kind==='Series'?'Show categories':'Movie categories';dialog.append(title);
        const close=document.createElement('button');close.textContent='Close';close.onclick=()=>dialog.close();dialog.append(close);
        const grid=document.createElement('div');grid.className='venomCategoryGrid';dialog.append(grid);
        for(const genre of cache.get(current.id)?.items||[]) {
            const link=document.createElement('a');link.dir='auto';link.textContent=genre.Name.replace(/^Venom: /,'');
            link.href=categoryUrl(genre.Id,current.id,current.kind,client.serverId());
            const count=document.createElement('small');count.textContent=String(genre[current.kind==='Series'?'SeriesCount':'MovieCount']||genre.ChildCount||0)+' titles';link.append(count);
            link.onclick=()=>dialog.close();grid.append(link);
        }
        dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);dialog.showModal();
    }
    function renameText(root,from,to) {
        const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
        while(walker.nextNode())if(walker.currentNode.nodeValue.trim()===from)walker.currentNode.nodeValue=to;
    }
    function run() {
        scheduled=false;
        const client=window.ApiClient;
        const uid=client?.getCurrentUserId?.();
        if(uid!==activeUser){cache.clear();activeUser=uid;document.querySelector('.venomCategoryDialog')?.remove();}
        const current=scope(location.hash,uid);
        if(!current) {
            document.querySelectorAll('.venomNavHidden').forEach(e=>{e.classList.remove('venomNavHidden');e.removeAttribute('aria-disabled');});
            document.querySelectorAll('.venomIndexNotice').forEach(e=>e.remove());
            document.querySelectorAll('.venomBrowseLinks').forEach(e=>e.remove());
            document.querySelectorAll('.venomLiveBrowseLinks').forEach(e=>e.remove());
            return;
        }
        // Jellyfin reads this LOCAL setting with precisely the same user prefix.
        // One-time migration only; respect subsequent user adjustments.
        pageSizePolicy(uid);
        if(current.kind==='live') {
            let state=cache.get('live');
            if(!state||Date.now()-state.time>300000) {
                state={time:Date.now(),items:state?.items||[]};cache.set('live',state);
                client.ajax({type:'GET',url:client.getUrl('LiveTvCategories'),dataType:'json'})
                    .then(items=>{state.items=items;schedule();}).catch(()=>{});
                client.ajax({type:'GET',url:client.getUrl('LiveTv/Channels',{UserId:uid,Limit:1,AddCurrentProgram:false,EnableImages:false}),dataType:'json'})
                    .then(result=>{state.total=result.TotalRecordCount;schedule();}).catch(()=>{});
            }
            const normalize=name=>name.replace(/\s+/g,' ').trim();
            const ranks=new Map(state.items.map((item,index)=>[normalize(item.name),index]));
            const page=document.getElementById('liveTvPage');
            if(page&&!page.querySelector('.venomLiveBrowseLinks')) {
                const nav=document.createElement('nav');nav.className='venomBrowseLinks venomLiveBrowseLinks';
                nav.setAttribute('aria-label','Venom Live TV browsing');
                const categories=document.createElement('a');categories.href='#/livetv?tab=0';
                categories.textContent='Browse channel categories';nav.append(categories);page.prepend(nav);
            }
            for(const link of page?.querySelectorAll('a.textActionButton[data-type="TvChannel"]')||[]) {
                const original=link.textContent;
                const card=link.closest('.card[data-type="TvChannel"]');
                const itemLink=card?.querySelector('a.cardImageContainer[aria-label]');
                const itemName=itemLink?.getAttribute('href')===link.getAttribute('href')?itemLink.getAttribute('aria-label'):null;
                const clean=channelCardName(original,itemName);
                if(clean!==original) {
                    link.textContent=clean;
                    link.title=clean;
                    link.setAttribute('aria-label',clean);
                }
                // Missing artwork has a separate numbered label. Clean only
                // leaf text in this same channel card, never its image/actions.
                for(const fallback of card?.querySelectorAll('.cardDefaultText')||[]) {
                    if(fallback.children.length)continue;
                    const label=channelCardName(fallback.textContent,itemName);
                    if(label!==fallback.textContent)fallback.textContent=label;
                }
            }
            const cards=[...(page?.querySelectorAll('.MuiPaper-root')||[])].filter(card=>ranks.has(normalize(card.querySelector('button .MuiTypography-body1')?.textContent||'')));
            if(cards.length===state.items.length&&cards.length) {
                const parent=cards[0].parentElement;
                if(cards.every(card=>card.parentElement===parent)) {
                    const sorted=[...cards].sort((a,b)=>ranks.get(normalize(a.querySelector('.MuiTypography-body1').textContent))-ranks.get(normalize(b.querySelector('.MuiTypography-body1').textContent)));
                    // Move existing keyed cards, not cloned buttons, retaining
                    // their React handlers and matching keyboard/visual order.
                    const all=[...parent.children].filter(card=>!cards.includes(card));
                    const desired=[...sorted.filter(card=>ranks.get(normalize(card.querySelector('.MuiTypography-body1').textContent))<state.items.filter(x=>x.id.startsWith('collection-')).length),...all,...sorted.filter(card=>ranks.get(normalize(card.querySelector('.MuiTypography-body1').textContent))>=state.items.filter(x=>x.id.startsWith('collection-')).length)];
                    if(desired.some((card,index)=>parent.children[index]!==card))desired.forEach(card=>parent.append(card));
                }
            }
            const status=page?.querySelector('[role="status"]');
            if(status&&Number.isInteger(state.total)&&/categories.*channels/i.test(status.textContent)) {
                const label=state.items.length+' categories · '+state.total.toLocaleString('en-US')+' channels';
                if(status.textContent!==label)status.textContent=label;
            }
        }
        let ready=false;
        if(current.id) {
            const old=cache.get(current.id);
            ready=old?.ready===true;
            if(!old||Date.now()-old.time>300000) {
                const state={time:Date.now(),ready,items:old?.items||[]};cache.set(current.id,state);
                client.ajax({type:'GET',url:client.getUrl('Genres',{UserId:uid,ParentId:current.id,IncludeItemTypes:current.kind,Recursive:true}),dataType:'json'})
                    .then(r=>{state.items=(r.Items||[]).filter(x=>(x.Name||'').startsWith('Venom:'));state.ready=state.items.length>0;schedule();})
                    .catch(()=>{}); // Unknown/offline: don't manufacture categories.
            }
        }
        for(const menu of document.querySelectorAll('[role="menu"]')) {
            const items=[...menu.children].filter(e=>e.matches('[role="menuitem"]'));
            const labels=items.map(e=>e.dataset.venomOriginal||e.textContent.trim());
            const known=current.kind==='live'
                ?labels.includes('Channels')&&labels.includes('Programs')&&labels.includes('Guide')
                :current.kind==='Movie'
                    ?labels.includes('Movies')&&labels.includes('Genres')&&labels.includes('Favorites')
                    :(labels.includes('Shows')||labels.includes('Series'))&&labels.includes('Genres')&&labels.includes('Upcoming');
            if(!known)continue;
            const hidden=hiddenLabels(current.kind,ready);
            items.forEach((item,i)=>{
                const label=labels[i];item.dataset.venomOriginal=label;
                const hide=hidden.includes(label);
                item.classList.toggle('venomNavHidden',hide);
                if(hide)item.setAttribute('aria-disabled','true');else item.removeAttribute('aria-disabled');
                if(label==='Programs')renameText(item,'Programs','Categories');
                if(label==='Genres'&&ready)renameText(item,'Genres','Categories');
            });
        }
        if(current.kind==='live') {
            document.querySelectorAll('header button').forEach(b=>renameText(b,'Programs','Categories'));
        }
        const page=document.getElementById(current.kind==='Movie'?'moviesPage':'tvshowsPage');
        document.querySelectorAll('.venomBrowseLinks').forEach(e=>{
            if(e.classList.contains('venomLiveBrowseLinks')&&current.kind==='live')return;
            if(!current.id||!page?.contains(e))e.remove();
        });
        if(current.id&&page&&!page.querySelector('.venomBrowseLinks')) {
            const nav=document.createElement('nav');nav.className='venomBrowseLinks';nav.setAttribute('aria-label','Venom browsing');
            const fav=document.createElement('a');fav.textContent=current.kind==='Series'?'Favourite shows':'Favourite movies';
            fav.href=favouritesUrl(current.kind,client.serverId());nav.append(fav);
            page.prepend(nav);
        }
        const nav=page?.querySelector('.venomBrowseLinks');
        if(current.id&&ready&&nav&&!nav.querySelector('[data-venom-categories]')) {
            const categories=document.createElement('a');categories.dataset.venomCategories='true';categories.textContent='Browse provider categories';
            const q=new URLSearchParams(current.params);q.set('tab',current.kind==='Series'?'3':'4');
            categories.href='#/'+(current.kind==='Series'?'tv':'movies')+'?'+q;
            categories.onclick=event=>{event.preventDefault();openCategories(current,client);};
            nav.append(categories);
        }
        document.querySelectorAll('.venomIndexNotice').forEach(e=>{if(ready||!current.id||!page?.contains(e))e.remove();});
        if(current.id&&!ready&&page&&!page.querySelector('.venomIndexNotice')) {
            const note=document.createElement('p');note.className='venomIndexNotice';
            note.textContent='Provider categories are still being indexed. Titles and favourites are available; categories will appear when ready.';
            page.prepend(note);
        }
    }
    function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(run);}}
    new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
    window.addEventListener('hashchange',schedule);
    window.addEventListener('pageshow',schedule);
    setInterval(()=>{if(!document.hidden)schedule();},30000);
    schedule();
})();
