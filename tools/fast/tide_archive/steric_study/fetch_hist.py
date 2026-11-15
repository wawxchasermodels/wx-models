import json, os, time, urllib.request
API="https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?application=wx_models_tides&time_zone=gmt&format=json"
ST=["9439040","9440910","9441102","9442396","9443090","9444090","9444900","9449880","9449424","9447130","9446484"]
CH=[("20190101","20191231"),("20200101","20201231"),("20210101","20211231"),("20220101","20221231"),("20230101","20230531")]
PR=[("hourly_height","&units=english&datum=MLLW"),("predictions","&units=english&datum=MLLW&interval=h"),("air_pressure","&units=metric&interval=h")]
def get(u):
    for i in range(4):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"wx-models-tides"}),timeout=120).read())
        except Exception as ex: err=ex; time.sleep(3+3*i)
    return {"error":str(err)}
for st in ST:
    fn=f"hist/{st}.json"
    out={p:{} for p,_ in PR}
    for p,ex in PR:
        for b,e in CH:
            j=get(f"{API}&product={p}&station={st}&begin_date={b}&end_date={e}{ex}")
            rows=j.get("predictions") or j.get("data") or []
            for r in rows:
                if r.get("v") not in ("",None): out[p][r["t"]]=float(r["v"])
            print(st,p,b,len(rows),flush=True)
    json.dump(out,open(fn,"w"))
