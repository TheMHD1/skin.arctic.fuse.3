"""Bounded decoded-frame and stream metadata sample, without storing URLs."""
import json
import re
import subprocess
import time

BIN=['docker','exec','jellyfin','/usr/lib/jellyfin-ffmpeg/ffprobe']
VIDEO='index,codec_type,codec_name,profile,level,width,height,coded_width,coded_height,pix_fmt,bits_per_raw_sample,field_order,r_frame_rate,avg_frame_rate,sample_aspect_ratio,display_aspect_ratio,color_range,color_space,color_transfer,color_primaries,chroma_location,bit_rate,sample_rate,channels,channel_layout,sample_fmt'
FRAME='media_type,stream_index,width,height,pix_fmt,color_range,color_space,color_transfer,color_primaries,chroma_location,interlaced_frame,top_field_first,best_effort_timestamp_time,pkt_duration_time,pkt_size'
_formats=None

def formats():
    global _formats
    if _formats is None:
        r=subprocess.run(BIN+['-v','error','-show_pixel_formats','-of','json'],capture_output=True,text=True,timeout=15)
        _formats={p['name']:p for p in json.loads(r.stdout)['pixel_formats']}
    return _formats

def side_data(rows):
    # Preserve technical numeric metadata (including DOVI layer flags and
    # mastering-display values), not arbitrary SEI text or tags.
    result=[]
    for row in rows:
        kind=str(row.get('side_data_type',''))[:100]
        if not re.fullmatch(r'[A-Za-z0-9 ()+_.:/-]*',kind):continue
        if not any(s in kind.lower() for s in ('mastering','content light','dovi','dolby','hdr','dynamic','ambient')):continue
        clean={'side_data_type':kind}
        for k,v in row.items():
            if k=='side_data_type':continue
            if isinstance(v,(int,float,bool)) or isinstance(v,str) and re.fullmatch(r'-?\d+(?:[./]\d+)?',v):clean[k]=v
        if clean not in result:result.append(clean)
    return result

def summarize(data,pixel_formats):
    streams=[]
    for s in data.get('streams',[]):
        row={k:s.get(k) for k in VIDEO.split(',')}
        row['language']=s.get('tags',{}).get('language')
        row['side_data']=side_data(s.get('side_data_list',[]))
        descriptor=pixel_formats.get(s.get('pix_fmt'),{})
        row['component_bit_depths']=[c['bit_depth'] for c in descriptor.get('components',[])] or None
        row['chroma_subsampling']=None
        if descriptor and not descriptor.get('flags',{}).get('rgb'):
            row['chroma_subsampling']={(1,1):'4:2:0',(1,0):'4:2:2',(0,0):'4:4:4'}.get((descriptor.get('log2_chroma_w'),descriptor.get('log2_chroma_h')))
        streams.append(row)
    frames=[f for f in data.get('frames',[]) if f.get('media_type')=='video']
    variants=[]
    for f in frames:
        v={k:f.get(k) for k in FRAME.split(',') if k not in ('best_effort_timestamp_time','pkt_duration_time','pkt_size','media_type')}
        v['side_data']=side_data(f.get('side_data_list',[]))
        descriptor=pixel_formats.get(f.get('pix_fmt'),{})
        v['component_bit_depths']=[c['bit_depth'] for c in descriptor.get('components',[])] or None
        if v not in variants:variants.append(v)
    transfers={f.get('color_transfer') for f in frames}
    hdr=bool(transfers&{'smpte2084','arib-std-b67'})
    sdr={'bt709','smpte170m','smpte240m','gamma22','gamma28','iec61966-2-1','bt2020-10','bt2020-12'}
    classification='hdr' if hdr else 'sdr' if transfers and transfers<=sdr else 'unknown_transfer'
    if len(frames)<3:classification='inconclusive_playback'
    samples=[]
    for index in sorted({f.get('stream_index',0) for f in frames}):
        group=[f for f in frames if f.get('stream_index',0)==index]
        sample={'stream_index':index,'decoded_frames':len(group),'observed_frame_rate':None,'encoded_video_bitrate_estimate_bps':None}
        try:
            timed=sorted(group,key=lambda f:float(f['best_effort_timestamp_time']))
            span=float(timed[-1]['best_effort_timestamp_time'])-float(timed[0]['best_effort_timestamp_time'])
            if span>=1:
                sample.update(observed_span_seconds=round(span,3),observed_frame_rate=round((len(timed)-1)/span,3))
                sizes=[int(f['pkt_size']) for f in timed[:-1]]
                if all(n>0 for n in sizes):sample['encoded_video_bitrate_estimate_bps']=round(sum(sizes)*8/span)
        except (KeyError,TypeError,ValueError,IndexError):pass
        samples.append(sample)
    return {'result':'working' if len(frames)>=3 else 'inconclusive_playback','classification':classification,
            'streams':streams,'decoded_video_frames':len(frames),'decoded_frame_variants':variants,
            'video_sample_statistics':samples,
            'format_reported':{k:data.get('format',{}).get(k) for k in ('format_name','bit_rate','nb_streams')},
            'bitrate_basis':'reported stream/container bitrate plus short-sample encoded video packet-size estimate when available; not network throughput or long-term average',
            'hdr_basis':'decoded-frame PQ/HLG transfer; side data retained separately; unknown is not SDR'}

def probe(url,seconds=35):
    started=time.monotonic()
    cmd=['docker','exec','jellyfin','timeout','--signal=TERM','--kill-after=3',str(seconds),'/usr/lib/jellyfin-ffmpeg/ffprobe',
         '-v','error','-rw_timeout','20000000','-analyzeduration','5000000','-probesize','4194304',
         '-read_intervals','%+5','-show_streams','-show_frames','-show_format','-show_entries',
         'stream='+VIDEO+':stream_tags=language:stream_side_data:frame='+FRAME+':frame_side_data:format=format_name,bit_rate,nb_streams',
         '-of','json',url]
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=seconds+8)
        if r.returncode!=0:return {'result':'inconclusive_playback','classification':'inconclusive_playback','exit_code':r.returncode,'seconds':round(time.monotonic()-started,2)}
        result=summarize(json.loads(r.stdout),formats())
        result.update(seconds=round(time.monotonic()-started,2),sample_requested_seconds=5)
        return result
    except subprocess.TimeoutExpired:
        return {'result':'inconclusive_timeout','classification':'inconclusive_playback','seconds':round(time.monotonic()-started,2)}
