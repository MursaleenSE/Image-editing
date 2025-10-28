import streamlit as st
from PIL import Image
import io
import base64
import requests
import os

# Debug + auto-detect auth for OpenAI / Replicate
import streamlit as st
import os
import requests

st.title("Auth debug — see masked tokens & test results")

def mask(s):
    if not s: return None
    s = s.strip()
    return f"{s[:4]}...{s[-4:]} (len={len(s)})"

# 1) read from possible locations
rep_token = st.secrets.get("api_keys", {}).get("REPLICATE_API_TOKEN") or st.secrets.get("REPLICATE_API_TOKEN") or os.environ.get("REPLICATE_API_TOKEN")
open_token = st.secrets.get("api_keys", {}).get("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")

# 2) sanitize (strip BOM/newlines)
def clean(t):
    if not t: return None
    return t.strip().replace("\ufeff", "")  # remove BOM if present

rep_token = clean(rep_token)
open_token = clean(open_token)

st.write("Replicate token present?", bool(rep_token))
st.write("Replicate token masked:", mask(rep_token))
st.write("OpenAI token present?", bool(open_token))
st.write("OpenAI token masked:", mask(open_token))

# 3) choose which provider to test
# If both present, we'll test both.
def test_openai(token):
    if not token: return None
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get("https://api.openai.com/v1/models", headers=headers, timeout=10)
        return (r.status_code, r.text[:400])
    except Exception as e:
        return ("error", str(e))

def test_replicate(token):
    if not token: return None
    headers = {"Authorization": f"Token {token}"}
    try:
        r = requests.get("https://api.replicate.com/v1/models", headers=headers, timeout=10)
        return (r.status_code, r.text[:400])
    except Exception as e:
        return ("error", str(e))

# Run tests (only very short responses shown)
open_result = test_openai(open_token)
rep_result = test_replicate(rep_token)

st.write("OpenAI test result (status, partial body):", open_result)
st.write("Replicate test result (status, partial body):", rep_result)

# 4) Helpful hints
if rep_token and (not rep_result or rep_result[0] in (401, "error")):
    st.warning("Replicate token present but test returned 401 or error. Check that:\n"
               "- You pasted the full token from Replicate dashboard (starts with r8_)\n"
               "- There are no extra quotes or spaces around it in Streamlit Secrets\n"
               "- You clicked Save in Streamlit Cloud -> Secrets and then clicked Rerun\n"
               "- If still failing, regenerate a new token on Replicate and paste that.")
if open_token and (not open_result or open_result[0] in (401, "error")):
    st.warning("OpenAI token present but test returned 401 or error. Check that:\n"
               "- You pasted the full OpenAI key (starts with sk-)\n"
               "- You used 'Bearer' as the header prefix\n"
               "- No extra quotes/spaces, and you saved secrets in Streamlit Cloud\n"
               "- If still failing, regenerate the key and update secrets.")
if not rep_token and not open_token:
    st.error("No tokens found. Re-open Streamlit Cloud -> Manage app -> Advanced -> Secrets and paste the TOML there.\n\n"
             "Example TOML (paste this exactly):\n\n"
             "[api_keys]\n"
             "REPLICATE_API_TOKEN = \"r8_your_full_token_here\"\n"
             "OPENAI_API_KEY    = \"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""
             "Then Save and Rerun the app.")

st.set_page_config(page_title="PhotoStyler", layout="centered")

st.title("PhotoStyler — upload a selfie, pick a style, get a portrait/cartoonic result")

# Upload
uploaded = st.file_uploader("Upload an image (jpg/png)", type=["jpg","jpeg","png"])
if not uploaded:
    st.info("Upload a photo to begin.")
    st.stop()

img = Image.open(uploaded).convert("RGB")
st.image(img, caption="Input image", use_column_width=True)

# Choose style
style = st.selectbox("Pick a style", ["Cartoon", "Oil painting", "Portrait / Studio", "Anime", "Pop-art"])
strength = st.slider("Transformation strength (higher = more change)", min_value=0.0, max_value=1.0, value=0.6)

if st.button("Transform"):
    with st.spinner("Calling model..."):
        # Example using Replicate's stable-diffusion-img2img model via their REST API.
        # You need to set REPLICATE_API_TOKEN in Streamlit secrets as st.secrets["api_keys"]["REPLICATE_API_TOKEN"]
        token = st.secrets["api_keys"]["REPLICATE_API_TOKEN"]

        # Convert image to bytes and base64 if needed
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()
        # For Replicate we typically upload the image (multipart) and call the model.
        # Simpler approach: use replicate python client (if installed) OR call their REST.
        # Below is a lightweight REST call to Replicate's predictions endpoint:
        headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
        }

        # Choose model and prompt per style
        prompt_map = {
            "Cartoon": "Convert this photo into a high-quality, colorful cartoon portrait, smooth lines, simplified shapes",
            "Oil painting": "Create a classic oil painting style portrait from this input photo, painterly brush strokes, rich texture",
            "Portrait / Studio": "Create a professional studio portrait from this input photo with soft lighting and neutral background",
            "Anime": "Convert this photo into an anime-style character, large expressive eyes, simplified shading",
            "Pop-art": "Create a pop-art style portrait with bold colors and halftone patterns"
        }
        prompt = prompt_map[style]

        # Using "stability-ai/stable-diffusion-img2img" on Replicate (public model)
        # POST to https://api.replicate.com/v1/predictions
        payload = {
            "version": "a9758d8b3f3b3c03d9b2b7f8a6f7c9c1b0d0e9a1", # placeholder version - ideally use the model's latest version id
            "input": {
                "image": "data:image/png;base64," + base64.b64encode(img_bytes).decode(),
                "prompt": prompt,
                "strength": float(strength),
                "num_inference_steps": 28
            }
        }

        # NOTE: The exact 'version' id and input keys depend on the model; consult Replicate model page for exact fields.
        resp = requests.post("https://api.replicate.com/v1/predictions", json=payload, headers=headers)
        if resp.status_code not in (200, 201):
            st.error(f"API error: {resp.status_code} - {resp.text}")
        else:
            result = resp.json()
            # Replicate returns a prediction object that may run async; for simplicity, poll until completed.
            prediction_url = f"https://api.replicate.com/v1/predictions/{result['id']}"
            import time
            while True:
                r = requests.get(prediction_url, headers=headers)
                rj = r.json()
                status = rj.get("status")
                if status == "succeeded":
                    output_urls = rj["output"]
                    # output may be list of URLs
                    out_url = output_urls[0]
                    st.image(out_url, caption="Transformed result", use_column_width=True)
                    st.markdown(f"[Download result]({out_url})")
                    break
                elif status == "failed":
                    st.error("Model failed: " + str(rj))
                    break
                else:
                    time.sleep(1)
                    # continue polling
