
import base64
from py_vapid import Vapid
from cryptography.hazmat.primitives import serialization

vapid = Vapid()
vapid.generate_keys()
vapid.save_key("private_key.pem")

public_bytes = vapid.public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint,
)

public_key = base64.urlsafe_b64encode(
    public_bytes
).rstrip(b"=").decode("ascii")

with open("vapid_public_key.txt", "w") as file:
    file.write(public_key)

print("VAPID keys created.")
print("Public key saved to vapid_public_key.txt")
print("Keep private_key.pem secret.")
