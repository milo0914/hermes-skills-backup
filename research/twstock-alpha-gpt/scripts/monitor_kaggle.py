#!/usr/bin/env python3
import os,time,subprocess,json,glob
OWNER,SLUG,OUT = "milo0914","twstock-v60-data-fetch","/tmp/kout"
os.makedirs(OUT,exist_ok=True)
print(f"監控 {OWNER}/{SLUG}...")
for i in range(60):
    r=subprocess.run(["python3","-m","kaggle","kernels","output",f"{OWNER}/{SLUG}","-p",OUT],capture_output=True,text=True)
    o=r.stdout+r.stderr
    if "still running" in o: print(f"[{i+1}/60] 執行中..."); time.sleep(60)
    elif os.path.exists(f"{OUT}/{SLUG}.log"):
        print("\n✓ 完成！"); 
        with open(f"{OUT}/{SLUG}.log") as f:
            for ln in f:
                try:
                    e=json.loads(ln)
                    if e.get("stream_name")=="stdout": print(e["data"],end="")
                except: pass
        csvs=glob.glob(f"{OUT}/*.csv")
        if csvs: print(f"\n✓ 產生 {len(csvs)} 個 CSV"); break
    else: time.sleep(30)
