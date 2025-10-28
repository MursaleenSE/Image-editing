# app.py (copy-paste this whole file)
import os
import time
import base64
import io
import requests
import streamlit as st
from PIL import Image

# Page config first (optional)
st.set_page_config(page_title="PhotoStyler", layout="centered")

# ---------- Helper functions ----------
def get_secret(name, table="api_keys"):
    """Try table in st.secrets, then top-level, then env var."""
    val = None
    try:
        val = st.secrets.get(table, {}).get(name)
    except Exception:
        val = st.secrets.get(name)
    if not val:
        val = os.environ.get(name)
    if isinstance(val, str):
        # strip whitespace and BOM just in case
        val = val.strip().replace("\ufeff", "")
    return val

def mask(s):
    if not s:
        return None
    s = s.strip()
    return f"{s[:4]}...{s[-4:]} (len={len(s)})"

# ---------- Debug / auth check (safe) ----------
st.title("Auth debug — masked tokens & test results")

rep_token = get_secret("REPLICATE_API_TOKEN")
open_token = get_secret("OPENAI_API_KEY")

st.write("Replicate token present?", bool(rep_token))
st.write("Replicate token masked:", mask(rep_token))
st.write("OpenAI token present?", bool(open_token))
st.write("OpenAI token masked:", mask(open_token))

def test_openai(token):
    if not token: return None
    try:
        r = requests.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        return (r.status_code, r.text[:400])
    except Exception as e:
        return ("error", str(e))

def test_replicate(token):
    if not token: return None
    try:
        r = requests.get("https://api.replicate.com/v1/models", headers={"Authorization": f"Token {token}"}, timeout=10)
        return (r.status_code, r.text[:400])
    except Exception as e:
        return ("error", str(e))

open_result = test_openai(open_token)
rep_result = test_replicate(rep_token)

st.write("OpenAI test result (status, partial body):", open_result)
st.write("Replicate test result (status, partial body):", rep_result)

if not rep_token and not open_token:
    st.error("No tokens found. See the TOML example below. DO NOT commit secrets.toml to GitHub.")
    st.code(
        '[api_keys]\n'
        'REPLICATE_API_TOKEN = "r8_your_full_token_here"\n'
        'OPENAI_API_KEY = "sk-your_full_key_here"\n',
        language="toml"
    )

# ---------- PhotoStyler UI ----------
st.title("PhotoStyler — upload a selfie, pick a style, get a portrait/cartoonic result")

uploaded = st.file_uploader("Upload an image (jpg/png)", type=["jpg", "jpeg", "png"])
if not uploaded:
    st.info("Upload a photo to begin.")
    st.stop()

img = Image.open(uploaded).convert("RGB")
st.image(img, caption="Input image", use_column_width=True)

style = st.selectbox("Pick a style", ["Cartoon", "Oil painting", "Portrait / Studio", "Anime", "Pop-art"])
strength = st.slider("Transformation strength (higher = more change)", min_value=0.0, max_value=1.0, value=0.6)

# ---------- When user clicks Transform ----------
if st.button("Transform"):
    with st.spinner("Calling model..."):
        # get replicate token safely (fall back to open token if you prefer openai endpoint)
        token = rep_token or open_token
        if not token:
            st.error("No API token found — please add it in Streamlit Cloud → Manage app → Advanced → Secrets and Rerun.")
            st.stop()

        # If the token starts with sk- assume OpenAI; if it starts with r8_ assume Replicate.
        if token.startswith("sk-"):
            provider = "openai"
        elif token.startswith("r8_"):
            provider = "replicate"
        else:
            provider = "unknown"

        # Convert image to bytes
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        # Build prompt based on style
        prompt_map = {
            "Cartoon": "Convert this photo into a high-quality, colorful cartoon portrait, smooth lines, simplified shapes",
            "Oil painting": "Create a classic oil painting style portrait from this input photo, painterly brush strokes, rich texture",
            "Portrait / Studio": "Create a professional studio portrait from this input photo with soft lighting and neutral background",
            "Anime": "Convert this photo into an anime-style character, large expressive eyes, simplified shading",
            "Pop-art": "Create a pop-art style portrait with bold colors and halftone patterns"
        }
        prompt = prompt_map[style]

        if provider == "replicate":
            # NOTE: Replace 'version' with the actual version id from the Replicate model page you choose.
            # Example below uses a placeholder and will not work until you set the real version.
            version_id = "REPLACE_WITH_REPLICATE_MODEL_VERSION_ID"
            if version_id.startswith("REPLACE"):
                st.error("You must set a real Replicate model 'version' id. Visit replicate.com, open your chosen model and copy the latest version id.")
                st.stop()

            payload = {
                "version": version_id,
                "input": {
                    "image": "data:image/png;base64," + base64.b64encode(img_bytes).decode(),
                    "prompt": prompt,
                    "strength": float(strength),
                    "num_inference_steps": 28
                }
            }
            headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
            resp = requests.post("https://api.replicate.com/v1/predictions", json=payload, headers=headers, timeout=60)

            if resp.status_code not in (200, 201):
                st.error(f"API error: {resp.status_code} - {resp.text}")
                st.stop()

            data = resp.json()
            # poll until completed
            prediction_url = f"https://api.replicate.com/v1/predictions/{data['id']}"
            while True:
                r = requests.get(prediction_url, headers=headers, timeout=60)
                rj = r.json()
                status = rj.get("status")
                if status == "succeeded":
                    output_urls = rj.get("output") or []
                    if output_urls:
                        out_url = output_urls[0]
                        st.image(out_url, caption="Transformed result", use_column_width=True)
                        st.markdown(f"[Download result]({out_url})")
                    else:
                        st.error("No output URL returned by the model.")
                    break
                elif status == "failed":
                    st.error("Model failed: " + str(rj))
                    break
                else:
                    time.sleep(1)

        elif provider == "openai":
            # Example sketch for OpenAI Images (check docs for exact parameters and endpoint)
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-image-1",  # adjust to your available model
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024"
            }
            r = requests.post("https://api.openai.com/v1/images/generations", headers=headers, json=payload, timeout=60)
            if r.status_code not in (200, 201):
                st.error(f"OpenAI API error: {r.status_code} - {r.text}")
                st.stop()
            jr = r.json()
            # OpenAI may return a data URL or URL; check their response format and adapt
            if "data" in jr and jr["data"]:
                img_b64 = jr["data"][0].get("b64_json")
                if img_b64:
                    img_bytes_out = base64.b64decode(img_b64)
                    st.image(img_bytes_out, caption="Result", use_column_width=True)
                    st.download_button("Download PNG", data=img_bytes_out, file_name="styled.png", mime="image/png")
                else:
                    st.error("No image bytes returned by OpenAI.")
            else:
                st.error("Unexpected OpenAI response: " + str(jr))

        else:
            st.error("Unrecognized token/provider. Make sure your token begins with 'r8_' for Replicate or 'sk-' for OpenAI.")
