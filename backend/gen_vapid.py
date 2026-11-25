"""Creates the key pair for web push messages (VAPID). Run it ONCE on any computer (or in the Codespaces terminal):

    python gen_vapid.py

Then put the two lines it prints into the Environment settings of your Render service.
The private key is a SECRET: never put it into GitHub or into the frontend.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


key = ec.generate_private_key(ec.SECP256R1())
private = key.private_numbers().private_value.to_bytes(32, "big")
public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
print("VAPID_PUBLIC_KEY=" + b64(public))
print("VAPID_PRIVATE_KEY=" + b64(private))
print("VAPID_SUBJECT=mailto:YOUR-EMAIL@example.com   (replace with your own address)")
