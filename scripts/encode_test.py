import base64,json,sys,time,pathlib
data = base64.b64decode(open(pathlib.Path("C:/Users/marco/Desktop/SuperEzio/scripts/comprehensive_ui_test.b64").resolve(),"r").read()).decode("utf-8")
exec(data)