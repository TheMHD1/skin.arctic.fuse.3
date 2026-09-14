"""Read-only check of native VOD provider categories and actual title results."""
import json
import runpy
from urllib.parse import urlencode

def main():
    api=runpy.run_path('/root/iptv-jellyfin-admin.py')['api']
    user=next(u for u in api('/Users') if u['Name'].casefold()=='habibi')
    for library in api('/Library/VirtualFolders'):
        if library['Name'] not in ('Venom Movies','Venom Series'):continue
        kind='Movie' if library['Name']=='Venom Movies' else 'Series'
        query=dict(UserId=user['Id'],ParentId=library['ItemId'],IncludeItemTypes=kind,Recursive=True)
        genres=api('/Genres?'+urlencode(query))['Items']
        provider=[g for g in genres if g['Name'].startswith('Venom: ')]
        if not provider:raise ValueError('Provider categories missing for '+library['Name'])
        failures=[];verified=0
        for genre in provider:
            page=api('/Users/'+user['Id']+'/Items?'+urlencode({**query,'GenreIds':genre['Id'],'Limit':1,'EnableImages':False,'Fields':'Genres'}))
            if not page['Items'] or page['TotalRecordCount']==0:
                failures.append({'name':genre['Name'],'id':genre['Id']})
            else:
                item=page['Items'][0]
                if item['Type']!=kind or genre['Name'].strip() not in {name.strip() for name in item.get('Genres',[])}:
                    print(json.dumps({'library':library['Name'],'requested_genre':genre['Name'],'returned_type':item['Type'],'returned_genres':item.get('Genres',[])},ensure_ascii=False),flush=True)
                    raise ValueError('Category query did not return the requested title type/genre')
                verified+=1
        print(json.dumps({'library':library['Name'],'provider_categories':len(provider),'verified_nonempty':verified,'empty_categories':failures},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
