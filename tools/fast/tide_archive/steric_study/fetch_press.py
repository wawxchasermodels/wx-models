import json, os, time, urllib.request
API="https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?application=wx_models_tides&time_zone=gmt&units=metric&format=json&interval=h&product=air_pressure"
ST=["9439040","9440910","9441102","9442396","9443090","9444090","9444900","9449880","9449424","9447130","9446484"]
CH=[("20230601","20240531"),("20240601","20250531"),("20250601","20260531"),("20260601","20261031")]
for st in ST:
    out={}
    for b,e in CH:
        u=f"{API}&station={st}&begin_date={b}&end_date={e}"
        for i in range(4):
            try:
                j=json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"wx-models-tides"}),timeout=120).read()); break
            except Exception as ex:
                j={"error":str(ex)}; time.sleep(3)
        for p in j.get("data") or []:
            if p.get("v") not in ("",None): out[p["t"]]=float(p["v"])
        print(st,b,len(j.get("data") or []), j.get("error",""),flush=True)
    json.dump(out,open(f"press/{st}.json","w"))
