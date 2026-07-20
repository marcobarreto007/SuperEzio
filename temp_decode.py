import base64, os
data = base64.b64decode("dGVzdCBjb250ZW50").decode()
print(data)
