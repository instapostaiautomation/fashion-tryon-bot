import os
import io
import json
import logging
import asyncio
import requests
from dotenv import load_dotenv
import random
import threading
import http.server
import urllib.parse

# Telegram libraries
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# AI SDKs
import fal_client
import google.generativeai as genai

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load local environment variables if available (.env file)
load_dotenv()

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {}

def save_config(config):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        pass

# --- Config & Environment Validation ---
config = load_config()
TELEGRAM_BOT_TOKEN = config.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
FAL_KEY = config.get("fal_key") or os.getenv("FAL_KEY")
GEMINI_API_KEY = config.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = config.get("openai_api_key") or os.getenv("OPENAI_API_KEY")

# Fallback defaults
MALE_MODEL_URL = config.get("male_model_url") or os.getenv("MALE_MODEL_URL", "https://fal.media/files/monkey/-LyhwXTRuc1nMzz26wUgR.png")
FEMALE_MODEL_URL = config.get("female_model_url") or os.getenv("FEMALE_MODEL_URL", "https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?auto=format&fit=crop&q=80&w=600")

# Setup API keys
if FAL_KEY:
    os.environ["FAL_KEY"] = FAL_KEY
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Validate mandatory variables
if not TELEGRAM_BOT_TOKEN or not FAL_KEY or not OPENAI_API_KEY:
    logger.error("CRITICAL: Missing essential keys (TELEGRAM_BOT_TOKEN, FAL_KEY, or OPENAI_API_KEY) in .env file!")

# load_config and save_config moved to top of file

# HTML for Admin Panel
ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title id="tab-title">Bot Control Panel</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0c10;
            --panel-bg: rgba(26, 27, 38, 0.75);
            --border-color: rgba(255, 255, 255, 0.08);
            --primary: #8a2be2;
            --primary-hover: #a14bf6;
            --accent: #00f0ff;
            --text-color: #f0f0f5;
            --text-muted: #8892b0;
            --shadow-glow: 0 8px 32px 0 rgba(138, 43, 226, 0.25);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }
        body {
            background: linear-gradient(135deg, #07080c 0%, #120e24 100%);
            color: var(--text-color);
            min-height: 100vh;
            padding: 1rem;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container {
            width: 100%;
            max-width: 1200px;
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            backdrop-filter: blur(20px);
            padding: 1.5rem;
            box-shadow: var(--shadow-glow);
            margin-top: 1rem;
        }
        header {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            width: 100%;
            max-width: 1200px;
            margin-bottom: 0.5rem;
            text-align: center;
        }
        @media(min-width: 768px) {
            header {
                flex-direction: row;
                justify-content: space-between;
                align-items: center;
                text-align: left;
                padding: 1rem 0;
            }
            .container {
                padding: 2.5rem;
            }
        }
        h1 { font-size: 2.2rem; font-weight: 800; background: linear-gradient(to right, #00f0ff, #8a2be2); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .subtitle { color: var(--text-muted); font-size: 1rem; margin-top: 0.2rem; }
        
        /* Navigation Tabs */
        .tabs {
            display: flex;
            overflow-x: auto;
            gap: 0.5rem;
            margin-bottom: 2rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 0.5rem;
            width: 100%;
            scrollbar-width: none; /* Firefox */
        }
        .tabs::-webkit-scrollbar { display: none; } /* Chrome/Safari */
        
        .tab-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 1rem;
            font-weight: 600;
            padding: 0.6rem 1.2rem;
            cursor: pointer;
            transition: all 0.3s ease;
            position: relative;
            white-space: nowrap;
        }
        .tab-btn.active { color: var(--text-color); }
        .tab-btn.active::after {
            content: '';
            position: absolute;
            bottom: -0.6rem;
            left: 0;
            width: 100%;
            height: 3px;
            background: linear-gradient(to right, #00f0ff, #8a2be2);
            border-radius: 3px;
        }
        
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        
        /* Grid Form Layout */
        .grid-2 {
            display: grid;
            grid-template-columns: 1fr;
            gap: 1.5rem;
        }
        @media(min-width: 992px) {
            .grid-2 { grid-template-columns: 1fr 1fr; }
        }
        
        .card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }
        .card-title {
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1.2rem;
            color: var(--accent);
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 0.5rem;
        }
        
        /* Form fields styling */
        .form-group {
            margin-bottom: 1.2rem;
        }
        label {
            display: block;
            font-size: 0.95rem;
            font-weight: 600;
            margin-bottom: 0.4rem;
            color: #d1d1d6;
        }
        .desc-text {
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-bottom: 0.4rem;
            line-height: 1.3;
        }
        input[type="text"], input[type="password"], textarea, select {
            width: 100%;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            color: var(--text-color);
            padding: 0.75rem 1rem;
            font-size: 0.95rem;
            transition: all 0.3s ease;
        }
        input[type="text"]:focus, input[type="password"]:focus, textarea:focus, select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 10px rgba(138, 43, 226, 0.2);
        }
        .checkbox-container {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            cursor: pointer;
            user-select: none;
            margin-top: 0.5rem;
        }
        .checkbox-container input {
            cursor: pointer;
            width: 18px;
            height: 18px;
            accent-color: var(--primary);
        }
        
        /* Buttons */
        .btn {
            background: linear-gradient(135deg, var(--primary) 0%, #6f1ab6 100%);
            color: white;
            border: none;
            padding: 0.8rem 2rem;
            font-size: 1rem;
            font-weight: 600;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(138, 43, 226, 0.3);
            width: 100%;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(138, 43, 226, 0.5);
            background: linear-gradient(135deg, var(--primary-hover) 0%, var(--primary) 100%);
        }
        @media(min-width: 768px) {
            .btn { width: auto; }
        }
        
        /* Toast notification */
        .toast {
            display: none;
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            background: #00f0ff;
            color: #0b0c10;
            padding: 1rem 2rem;
            border-radius: 10px;
            font-weight: 600;
            box-shadow: 0 5px 25px rgba(0, 240, 255, 0.4);
            z-index: 1000;
            animation: slideIn 0.3s ease;
        }
        @keyframes slideIn {
            from { transform: translateY(50px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        .badge {
            background: rgba(0, 240, 255, 0.1);
            color: var(--accent);
            padding: 0.2rem 0.6rem;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 600;
        }
    </style>
</head>
<body>
    <header>
        <div>
            <h1 id="header-title">Bot Control Panel</h1>
            <p class="subtitle" id="header-subtitle">Fully Dynamic Control Panel</p>
        </div>
        <div>
            <span class="badge">Dynamic Rebrand v2.0</span>
        </div>
    </header>

    <div class="container">
        <!-- Gender Switcher for Prompt Editing -->
        <div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; gap: 1rem; background: rgba(255,255,255,0.02); padding: 1rem; border-radius: 12px; border: 1px solid rgba(255,255,255,0.04);">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <label for="prompt_gender" style="margin-bottom: 0;">👥 Edit Prompts For:</label>
                <select id="prompt_gender" style="width: 180px; padding: 0.4rem 0.8rem;" onchange="togglePromptGender()">
                    <option value="male">👨 Male Model</option>
                    <option value="female">👩 Female Model</option>
                </select>
            </div>
            <div>
                <p style="font-size: 0.85rem; color: var(--text-muted);">Switch gender to edit their respective prompt lists.</p>
            </div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('branding')">🎨 Branding & UI</button>
            <button class="tab-btn" onclick="switchTab('bot')">🤖 Bot Behavior</button>
            <button class="tab-btn" onclick="switchTab('video')">🎥 Video & AI</button>
            <button class="tab-btn" onclick="switchTab('api')">🔐 API Credentials</button>
            <button class="tab-btn" onclick="switchTab('prompts')">📝 Prompts Editor</button>
            <button class="tab-btn" onclick="switchTab('models')">📸 Base Models</button>
        </div>

        <form onsubmit="saveConfig(event)">
            <!-- Branding Tab -->
            <div id="tab-branding" class="tab-content active">
                <div class="card">
                    <div class="card-title">🎨 Admin Panel Customization & Branding</div>
                    <div class="grid-2">
                        <div class="form-group">
                            <label>Admin Panel Title</label>
                            <div class="desc-text">Custom name displayed at the top of this dashboard.</div>
                            <input type="text" id="admin_panel_title" placeholder="Instapostai">
                        </div>
                        <div class="form-group">
                            <label>Admin Panel Subtitle</label>
                            <div class="desc-text">Subtitle displayed below the title.</div>
                            <input type="text" id="admin_panel_subtitle" placeholder="Bot Admin Control Panel">
                        </div>
                    </div>
                </div>
            </div>

            <!-- Bot Behavior Tab -->
            <div id="tab-bot" class="tab-content">
                <div class="card">
                    <div class="card-title">🤖 Telegram Bot UI & Interactions</div>
                    <div class="form-group">
                        <label>Telegram /start Welcome Message</label>
                        <div class="desc-text">Text sent to users when they join or click /start. Supports markdown formatting.</div>
                        <textarea id="telegram_start_text" style="height: 180px;"></textarea>
                    </div>
                    <div class="grid-2">
                        <div class="form-group">
                            <label>Tops (Upper Body) Behavior</label>
                            <div class="desc-text">What happens when a top garment is uploaded?</div>
                            <select id="default_upper_category">
                                <option value="ask">Ask User (Shirt vs T-Shirt menu)</option>
                                <option value="shirt">Auto-Select Shirt (Skip menu)</option>
                                <option value="tshirt">Auto-Select T-Shirt (Skip menu)</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Bottoms (Lower Body) Behavior</label>
                            <div class="desc-text">What happens when a bottom garment is uploaded?</div>
                            <select id="default_lower_category">
                                <option value="ask">Ask User (Cargo, Jeans, Trouser, Shorts menu)</option>
                                <option value="jeans">Auto-Select Jeans (Skip menu)</option>
                                <option value="cargo">Auto-Select Cargo (Skip menu)</option>
                                <option value="trouser">Auto-Select Trouser (Skip menu)</option>
                                <option value="shorts">Auto-Select Shorts (Skip menu)</option>
                            </select>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Video & AI Settings Tab -->
            <div id="tab-video" class="tab-content">
                <div class="card">
                    <div class="card-title">🎥 Video Reel & Catwalk Settings</div>
                    <div class="grid-2">
                        <div class="form-group">
                            <label>Video Duration (Seconds)</label>
                            <div class="desc-text">Choose video clip length. Note: 10s uses double the Fal.ai credits as 5s. Kling AI Pro supports up to 10s max.</div>
                            <select id="video_duration">
                                <option value="5">5 Seconds (Fast & Cost Efficient)</option>
                                <option value="10">10 Seconds (Slow Catwalk Poses)</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Elegant Slow-Motion mode</label>
                            <div class="desc-text">Injects slow motion pacing, fabric dynamics, and steady catalog cameras.</div>
                            <label class="checkbox-container">
                                <input type="checkbox" id="video_slow_motion"> Enable Slow Motion
                            </label>
                        </div>
                    </div>
                    <div class="grid-2" style="margin-top: 1rem;">
                        <div class="form-group">
                            <label>AI Generation Resolution</label>
                            <div class="desc-text">Resolution for fallback gpt-image-1 portrait generations.</div>
                            <select id="image_size">
                                <option value="1024x1024">1024x1024 (1:1 Square Post)</option>
                                <option value="1024x1536">1024x1536 (2:3 Vertical Catalog - Recommended)</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Run Mode Engine</label>
                            <div class="desc-text">VTON and Video engine selector.</div>
                            <select id="run_mode">
                                <option value="premium">Premium Mode (FASHN Tryon / Kling Pro Video)</option>
                                <option value="budget">Budget Mode (CatVTON / Wan Video)</option>
                                <option value="supersaver">Super Saver Mode (CatVTON / SVD Video)</option>
                            </select>
                        </div>
                    </div>
                </div>
            </div>

            <!-- API Credentials Tab -->
            <div id="tab-api" class="tab-content">
                <div class="card">
                    <div class="card-title">🔐 API Access Tokens & Keys</div>
                    <div class="desc-text" style="color: #ff453a; font-weight: 600; margin-bottom: 1.2rem;">⚠️ Changing critical API credentials or Telegram tokens will trigger an automatic self-restart of the bot process.</div>
                    <div class="grid-2">
                        <div class="form-group">
                            <label>Telegram Bot HTTP API Token</label>
                            <input type="password" id="telegram_bot_token" placeholder="Leave empty to use .env value">
                        </div>
                        <div class="form-group">
                            <label>Fal.ai API Key</label>
                            <input type="password" id="fal_key" placeholder="Leave empty to use .env value">
                        </div>
                    </div>
                    <div class="grid-2">
                        <div class="form-group">
                            <label>Google Gemini API Key</label>
                            <input type="password" id="gemini_api_key" placeholder="Leave empty to use .env value">
                        </div>
                        <div class="form-group">
                            <label>OpenAI API Key</label>
                            <input type="password" id="openai_api_key" placeholder="Leave empty to use config value">
                        </div>
                    </div>
                    <div class="grid-2">
                        <div class="form-group">
                            <label>Instagram Business Account ID</label>
                            <input type="text" id="instagram_business_account_id">
                        </div>
                        <div class="form-group">
                            <label>Meta Graph API Access Token</label>
                            <input type="password" id="meta_access_token">
                        </div>
                    </div>
                </div>
            </div>

            <!-- Prompts Editor Tab -->
            <div id="tab-prompts" class="tab-content">
                <!-- Shirt -->
                <div class="card">
                    <div class="card-title">👕 Shirt settings</div>
                    <div class="form-group">
                        <label>Image Prompt (OpenAI DALL-E-3 / fallback)</label>
                        <textarea id="imgprompt-shirt" style="height: 100px;"></textarea>
                    </div>
                    <div class="grid-2">
                        <div class="form-group">
                            <label>Video Motion Prompt</label>
                            <textarea id="prompt-shirt" style="height: 80px;"></textarea>
                        </div>
                        <div class="form-group">
                            <label>Video Negative Prompt</label>
                            <textarea id="neg-shirt" style="height: 80px;"></textarea>
                        </div>
                    </div>
                </div>
                
                <!-- T-Shirt -->
                <div class="card">
                    <div class="card-title">👕 T-Shirt Settings</div>
                    <div class="form-group">
                        <label>Image Prompt (OpenAI DALL-E-3 / fallback)</label>
                        <textarea id="imgprompt-tshirt" style="height: 100px;"></textarea>
                    </div>
                    <div class="grid-2">
                        <div class="form-group">
                            <label>Video Motion Prompt</label>
                            <textarea id="prompt-tshirt" style="height: 80px;"></textarea>
                        </div>
                        <div class="form-group">
                            <label>Video Negative Prompt</label>
                            <textarea id="neg-tshirt" style="height: 80px;"></textarea>
                        </div>
                    </div>
                </div>

                <!-- Jeans -->
                <div class="card">
                    <div class="card-title">👖 Jeans Settings</div>
                    <div class="form-group">
                        <label>Image Prompt</label>
                        <textarea id="imgprompt-jeans" style="height: 100px;"></textarea>
                    </div>
                    <div class="grid-2">
                        <div class="form-group">
                            <label>Video Motion Prompt</label>
                            <textarea id="prompt-jeans" style="height: 80px;"></textarea>
                        </div>
                        <div class="form-group">
                            <label>Video Negative Prompt</label>
                            <textarea id="neg-jeans" style="height: 80px;"></textarea>
                        </div>
                    </div>
                </div>

                <!-- Cargo -->
                <div class="card">
                    <div class="card-title">👖 Cargo Settings</div>
                    <div class="form-group">
                        <label>Image Prompt</label>
                        <textarea id="imgprompt-cargo" style="height: 100px;"></textarea>
                    </div>
                    <div class="grid-2">
                        <div class="form-group">
                            <label>Video Motion Prompt</label>
                            <textarea id="prompt-cargo" style="height: 80px;"></textarea>
                        </div>
                        <div class="form-group">
                            <label>Video Negative Prompt</label>
                            <textarea id="neg-cargo" style="height: 80px;"></textarea>
                        </div>
                    </div>
                </div>

                <!-- Trouser -->
                <div class="card">
                    <div class="card-title">👖 Trouser Settings</div>
                    <div class="form-group">
                        <label>Image Prompt</label>
                        <textarea id="imgprompt-trouser" style="height: 100px;"></textarea>
                    </div>
                    <div class="grid-2">
                        <div class="form-group">
                            <label>Video Motion Prompt</label>
                            <textarea id="prompt-trouser" style="height: 80px;"></textarea>
                        </div>
                        <div class="form-group">
                            <label>Video Negative Prompt</label>
                            <textarea id="neg-trouser" style="height: 80px;"></textarea>
                        </div>
                    </div>
                </div>

                <!-- Shorts -->
                <div class="card">
                    <div class="card-title">🩳 Shorts Settings</div>
                    <div class="form-group">
                        <label>Image Prompt</label>
                        <textarea id="imgprompt-shorts" style="height: 100px;"></textarea>
                    </div>
                    <div class="grid-2">
                        <div class="form-group">
                            <label>Video Motion Prompt</label>
                            <textarea id="prompt-shorts" style="height: 80px;"></textarea>
                        </div>
                        <div class="form-group">
                            <label>Video Negative Prompt</label>
                            <textarea id="neg-shorts" style="height: 80px;"></textarea>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Models Tab -->
            <div id="tab-models" class="tab-content">
                <div class="card">
                    <div class="card-title">📸 Base Model Configuration</div>
                    <div class="form-group">
                        <label>Male Model Image URL</label>
                        <input type="text" id="male_model_url">
                    </div>
                    <div class="form-group">
                        <label>Female Model Image URL</label>
                        <input type="text" id="female_model_url">
                    </div>
                    <div class="form-group">
                        <label>Instagram Auto-Posting</label>
                        <select id="skip_instagram_post">
                            <option value="true">Disable (Telegram Showcase Only)</option>
                            <option value="false">Enable (Automatic Reels Post)</option>
                        </select>
                    </div>
                </div>
            </div>

            <div style="text-align: right; margin-top: 1rem; margin-bottom: 2rem;">
                <button type="submit" class="btn">Save & Apply Configuration</button>
            </div>
        </form>
    </div>

    <div id="toast" class="toast">Settings Saved & Applied Successfully!</div>

    <script>
        let configData = {};
        let activePromptGender = 'male';

        function cacheCurrentPrompts() {
            const promptKey = activePromptGender + '_prompts';
            if (!configData[promptKey]) {
                configData[promptKey] = {};
            }
            const garments = ['shirt', 'tshirt', 'jeans', 'cargo', 'trouser', 'shorts'];
            garments.forEach(g => {
                configData[promptKey][g] = {
                    image_prompt: document.getElementById(`imgprompt-${g}`).value.trim(),
                    prompt: document.getElementById(`prompt-${g}`).value.trim(),
                    negative_prompt: document.getElementById(`neg-${g}`).value.trim()
                };
            });
        }

        function loadPromptsForSelectedGender() {
            const promptKey = activePromptGender + '_prompts';
            const promptsObj = configData[promptKey] || {};

            const garments = ['shirt', 'tshirt', 'jeans', 'cargo', 'trouser', 'shorts'];
            garments.forEach(g => {
                const gp = promptsObj[g] || {};
                document.getElementById(`imgprompt-${g}`).value = gp.image_prompt || '';
                document.getElementById(`prompt-${g}`).value = gp.prompt || '';
                document.getElementById(`neg-${g}`).value = gp.negative_prompt || '';
            });
        }

        function togglePromptGender() {
            cacheCurrentPrompts();
            activePromptGender = document.getElementById('prompt_gender').value;
            loadPromptsForSelectedGender();
        }

        async function fetchConfig() {
            try {
                const res = await fetch('/api/config');
                configData = await res.json();

                // Rebrand Admin Panel Elements
                const titleText = configData.admin_panel_title || "Bot Control Panel";
                const subtitleText = configData.admin_panel_subtitle || "Fully Dynamic Control Panel";
                document.getElementById('tab-title').innerText = titleText;
                document.getElementById('header-title').innerText = titleText;
                document.getElementById('header-subtitle').innerText = subtitleText;

                // Load basic inputs
                document.getElementById('admin_panel_title').value = configData.admin_panel_title || '';
                document.getElementById('admin_panel_subtitle').value = configData.admin_panel_subtitle || '';
                document.getElementById('telegram_start_text').value = configData.telegram_start_text || '';
                
                document.getElementById('default_upper_category').value = configData.default_upper_category || 'ask';
                document.getElementById('default_lower_category').value = configData.default_lower_category || 'ask';
                
                document.getElementById('video_duration').value = String(configData.video_duration || '5');
                document.getElementById('video_slow_motion').checked = !!configData.video_slow_motion;
                document.getElementById('image_size').value = configData.image_size || '1024x1536';
                document.getElementById('run_mode').value = configData.run_mode || 'premium';

                document.getElementById('male_model_url').value = configData.male_model_url || '';
                document.getElementById('female_model_url').value = configData.female_model_url || '';
                document.getElementById('skip_instagram_post').value = String(configData.skip_instagram_post);

                // API tokens
                document.getElementById('telegram_bot_token').value = configData.telegram_bot_token || '';
                document.getElementById('fal_key').value = configData.fal_key || '';
                document.getElementById('gemini_api_key').value = configData.gemini_api_key || '';
                document.getElementById('openai_api_key').value = configData.openai_api_key || '';
                document.getElementById('instagram_business_account_id').value = configData.instagram_business_account_id || '';
                document.getElementById('meta_access_token').value = configData.meta_access_token || '';

                document.getElementById('prompt_gender').value = activePromptGender;
                loadPromptsForSelectedGender();
            } catch (err) {
                console.error("Failed to load config:", err);
            }
        }

        async function saveConfig(event) {
            event.preventDefault();

            cacheCurrentPrompts();

            const updatedConfig = {
                ...configData,
                admin_panel_title: document.getElementById('admin_panel_title').value.trim(),
                admin_panel_subtitle: document.getElementById('admin_panel_subtitle').value.trim(),
                telegram_start_text: document.getElementById('telegram_start_text').value,
                
                default_upper_category: document.getElementById('default_upper_category').value,
                default_lower_category: document.getElementById('default_lower_category').value,
                
                video_duration: parseInt(document.getElementById('video_duration').value, 10),
                video_slow_motion: document.getElementById('video_slow_motion').checked,
                image_size: document.getElementById('image_size').value,
                run_mode: document.getElementById('run_mode').value,

                male_model_url: document.getElementById('male_model_url').value.trim(),
                female_model_url: document.getElementById('female_model_url').value.trim(),
                skip_instagram_post: document.getElementById('skip_instagram_post').value === 'true',

                telegram_bot_token: document.getElementById('telegram_bot_token').value.trim(),
                fal_key: document.getElementById('fal_key').value.trim(),
                gemini_api_key: document.getElementById('gemini_api_key').value.trim(),
                openai_api_key: document.getElementById('openai_api_key').value.trim(),
                instagram_business_account_id: document.getElementById('instagram_business_account_id').value.trim(),
                meta_access_token: document.getElementById('meta_access_token').value.trim()
            };

            try {
                const res = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(updatedConfig)
                });

                const result = await res.json();
                if (result.status === 'success') {
                    showToast();
                    // Reload title and subtitle instantly
                    const newTitle = updatedConfig.admin_panel_title || "Bot Control Panel";
                    const newSubtitle = updatedConfig.admin_panel_subtitle || "Fully Dynamic Control Panel";
                    document.getElementById('tab-title').innerText = newTitle;
                    document.getElementById('header-title').innerText = newTitle;
                    document.getElementById('header-subtitle').innerText = newSubtitle;
                } else {
                    alert('Error saving config: ' + result.message);
                }
            } catch (err) {
                alert('Request failed: ' + err);
            }
        }

        function showToast() {
            const toast = document.getElementById('toast');
            toast.style.display = 'block';
            setTimeout(() => {
                toast.style.display = 'none';
            }, 3000);
        }

        function switchTab(tabId) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            event.currentTarget.classList.add('active');
            document.getElementById(`tab-${tabId}`).classList.add('active');
        }

        fetchConfig();
    </script>
</body>
</html>"""

APP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title id="tab-title">AI Try-On Studio</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0c10;
            --panel-bg: rgba(26, 27, 38, 0.7);
            --border-color: rgba(255, 255, 255, 0.08);
            --primary: #8a2be2;
            --primary-hover: #a14bf6;
            --accent: #00f0ff;
            --text-color: #f0f0f5;
            --text-muted: #8892b0;
            --shadow-glow: 0 8px 32px 0 rgba(138, 43, 226, 0.2);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }
        body {
            background: linear-gradient(135deg, #07080c 0%, #120e24 100%);
            color: var(--text-color);
            min-height: 100vh;
            padding: 1rem;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            width: 100%;
            max-width: 1200px;
            margin-bottom: 1rem;
            padding: 1rem 0;
            border-bottom: 1px solid var(--border-color);
        }
        h1 { font-size: 2.2rem; font-weight: 800; background: linear-gradient(to right, #00f0ff, #8a2be2); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .subtitle { color: var(--text-muted); font-size: 0.95rem; margin-top: 0.2rem; }
        .admin-link {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            color: var(--text-color);
            padding: 0.5rem 1.2rem;
            border-radius: 10px;
            text-decoration: none;
            font-weight: 600;
            transition: all 0.3s ease;
            font-size: 0.9rem;
        }
        .admin-link:hover {
            background: var(--primary);
            border-color: var(--primary);
            box-shadow: var(--shadow-glow);
        }
        .main-container {
            width: 100%;
            max-width: 1200px;
            display: grid;
            grid-template-columns: 1fr;
            gap: 2rem;
            margin-top: 1rem;
        }
        @media(min-width: 992px) {
            .main-container { grid-template-columns: 1fr 1fr; }
        }
        .card {
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 2rem;
            backdrop-filter: blur(20px);
            box-shadow: var(--shadow-glow);
        }
        .card-title {
            font-size: 1.3rem;
            font-weight: 800;
            margin-bottom: 1.5rem;
            color: var(--accent);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        /* Upload Area */
        .upload-area {
            border: 2px dashed var(--border-color);
            border-radius: 14px;
            padding: 2.5rem 1.5rem;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            background: rgba(0, 0, 0, 0.2);
            position: relative;
            margin-bottom: 1.5rem;
        }
        .upload-area:hover {
            border-color: var(--accent);
            background: rgba(0, 240, 255, 0.02);
        }
        .upload-icon { font-size: 2.5rem; margin-bottom: 1rem; color: var(--text-muted); }
        .upload-area input[type="file"] { display: none; }
        .preview-img {
            max-width: 100%;
            max-height: 250px;
            border-radius: 10px;
            display: none;
            margin-top: 1rem;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
        }
        
        /* Form styling */
        .form-group { margin-bottom: 1.2rem; }
        label { display: block; font-size: 0.95rem; font-weight: 600; margin-bottom: 0.4rem; color: #d1d1d6; }
        select, textarea {
            width: 100%;
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            color: var(--text-color);
            padding: 0.75rem 1rem;
            font-size: 0.95rem;
            transition: all 0.3s ease;
        }
        select:focus, textarea:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 10px rgba(138, 43, 226, 0.2);
        }
        
        /* Gender buttons */
        .gender-selector { display: flex; gap: 1rem; margin-bottom: 1.2rem; }
        .gender-btn {
            flex: 1;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--border-color);
            color: var(--text-muted);
            padding: 0.8rem;
            border-radius: 10px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
            text-align: center;
        }
        .gender-btn.active {
            background: linear-gradient(135deg, var(--primary) 0%, #6f1ab6 100%);
            border-color: var(--primary);
            color: white;
            box-shadow: 0 4px 15px rgba(138, 43, 226, 0.3);
        }
        
        /* Buttons & Loaders */
        .btn {
            background: linear-gradient(135deg, var(--primary) 0%, #6f1ab6 100%);
            color: white;
            border: none;
            padding: 0.9rem 2rem;
            font-size: 1rem;
            font-weight: 600;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(138, 43, 226, 0.3);
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
        }
        .btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(138, 43, 226, 0.5);
            background: linear-gradient(135deg, var(--primary-hover) 0%, var(--primary) 100%);
        }
        .btn:disabled {
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-muted);
            border: 1px solid var(--border-color);
            cursor: not-allowed;
            box-shadow: none;
        }
        
        /* Spinner */
        .spinner {
            border: 3px solid rgba(255, 255, 255, 0.1);
            width: 24px;
            height: 24px;
            border-radius: 50%;
            border-left-color: var(--accent);
            animation: spin 1s linear infinite;
            display: none;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        
        /* Result Preview */
        .result-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            border: 2px dashed var(--border-color);
            background: rgba(0, 0, 0, 0.2);
            border-radius: 14px;
            min-height: 400px;
            position: relative;
            overflow: hidden;
            width: 100%;
        }
        .result-img, .result-video {
            max-width: 100%;
            max-height: 550px;
            border-radius: 10px;
            display: none;
            box-shadow: 0 8px 30px rgba(0,0,0,0.6);
        }
        .placeholder-text {
            color: var(--text-muted);
            text-align: center;
            padding: 2rem;
        }
        .action-row {
            display: flex;
            gap: 1rem;
            width: 100%;
            margin-top: 1.5rem;
        }
        
        /* Status message overlay */
        .status-overlay {
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(11, 12, 16, 0.85);
            display: none;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 1rem;
            color: var(--text-color);
            font-weight: 600;
            z-index: 10;
        }
    </style>
</head>
<body>
    <header>
        <div>
            <h1 id="header-title">AI Try-On Studio</h1>
            <p class="subtitle" id="header-subtitle">VTON & Video Catalog Generator</p>
        </div>
        <div>
            <a href="/admin" class="admin-link">⚙️ Control Panel</a>
        </div>
    </header>

    <div class="main-container">
        <!-- Left: Upload & Config -->
        <div class="card">
            <div class="card-title">👕 Upload Garment</div>
            
            <div class="upload-area" onclick="document.getElementById('file-input').click()">
                <div class="upload-icon">📤</div>
                <p style="font-weight: 600;">Drag & drop garment photo or click to upload</p>
                <p class="subtitle" style="font-size: 0.8rem;">PNG, JPG, JPEG (Hanger or Flat-lay)</p>
                <input type="file" id="file-input" accept="image/*" onchange="handleFileUpload(event)">
                <img id="garment-preview" class="preview-img" alt="Garment Preview">
            </div>

            <div id="settings-section" style="opacity: 0.5; pointer-events: none; transition: all 0.3s ease;">
                <div class="card-title">⚙️ Generation Settings</div>
                
                <label>Target Model Gender</label>
                <div class="gender-selector">
                    <button class="gender-btn active" id="gender-male" onclick="setGender('male')">👨 Male Model</button>
                    <button class="gender-btn" id="gender-female" onclick="setGender('female')">👩 Female Model</button>
                </div>

                <div class="grid-2" style="display: grid; grid-template-columns: 1fr; gap: 1rem;">
                    <div class="form-group">
                        <label>Garment Category</label>
                        <select id="sub_type">
                            <option value="shirt">👕 Shirt</option>
                            <option value="tshirt">👕 T-Shirt / Polo</option>
                            <option value="jeans">👖 Jeans</option>
                            <option value="cargo">👖 Cargo Pants</option>
                            <option value="trouser">👖 Trouser</option>
                            <option value="shorts">🩳 Shorts</option>
                        </select>
                    </div>
                </div>

                <div class="form-group" style="margin-top: 0.5rem;">
                    <label>Garment AI Description</label>
                    <textarea id="garment_desc" style="height: 90px;" placeholder="AI description will load automatically..."></textarea>
                </div>

                <button class="btn" id="generate-tryon-btn" disabled onclick="generateTryon()">
                    <div class="spinner" id="tryon-spinner"></div>
                    <span id="tryon-btn-text">🎨 Generate Try-On Model</span>
                </button>
            </div>
        </div>

        <!-- Right: Results -->
        <div class="card" style="display: flex; flex-direction: column; align-items: center;">
            <div class="card-title" style="width: 100%;">📸 Output Preview</div>
            
            <div class="result-container" id="result-box">
                <div class="status-overlay" id="status-overlay">
                    <div class="spinner" id="overlay-spinner" style="display: block; width: 40px; height: 40px;"></div>
                    <p id="status-text">Processing VTON...</p>
                </div>
                
                <div class="placeholder-text" id="placeholder-text">
                    <p style="font-size: 4rem; margin-bottom: 1rem;">✨</p>
                    <p style="font-weight: 600; font-size: 1.1rem;">Your AI Model Image will appear here</p>
                    <p class="subtitle" style="font-size: 0.85rem;">Upload a garment and click Generate Try-On</p>
                </div>
                
                <img id="result-image" class="result-img" alt="Generated VTON Model">
                <video id="result-video" class="result-video" controls loop></video>
            </div>

            <!-- Action buttons -->
            <div class="action-row" id="tryon-actions" style="display: none;">
                <button class="btn" onclick="downloadImage()">💾 Download Image</button>
                <button class="btn" id="generate-video-btn" onclick="generateVideo()" style="background: linear-gradient(135deg, #00f0ff 0%, #00b8d4 100%); color: #0b0c10; box-shadow: 0 4px 15px rgba(0, 240, 255, 0.25);">
                    <div class="spinner" id="video-spinner" style="border-left-color: #0b0c10;"></div>
                    <span id="video-btn-text">🎬 Generate Catwalk Video Reel</span>
                </button>
            </div>

            <div class="action-row" id="video-actions" style="display: none;">
                <button class="btn" onclick="downloadVideo()">💾 Download Catwalk Video</button>
                <button class="btn" onclick="resetStudio()" style="background: rgba(255,255,255,0.05); border: 1px solid var(--border-color); color: var(--text-color); box-shadow: none;">🔄 Start Over</button>
            </div>
        </div>
    </div>

    <script>
        let uploadedGarmentUrl = "";
        let generatedModelUrl = "";
        let generatedVideoUrl = "";
        let selectedGender = "male";

        async function fetchBranding() {
            try {
                const res = await fetch('/api/config');
                const config = await res.json();
                const titleText = config.admin_panel_title || "AI Try-On Studio";
                document.getElementById('tab-title').innerText = titleText + " - VTON App";
                document.getElementById('header-title').innerText = titleText + " Studio";
            } catch(e) {}
        }
        fetchBranding();

        function setGender(gender) {
            selectedGender = gender;
            document.querySelectorAll('.gender-btn').forEach(btn => btn.classList.remove('active'));
            if (gender === 'male') {
                document.getElementById('gender-male').classList.add('active');
            } else {
                document.getElementById('gender-female').classList.add('active');
            }
        }

        async function handleFileUpload(event) {
            const file = event.target.files[0];
            if (!file) return;

            // Show local preview
            const reader = new FileReader();
            reader.onload = function(e) {
                const preview = document.getElementById('garment-preview');
                preview.src = e.target.result;
                preview.style.display = 'block';
            };
            reader.readAsDataURL(file);

            // Set loading state for classification
            document.getElementById('status-overlay').style.display = 'flex';
            document.getElementById('status-text').innerText = "Uploading & Analyzing Garment...";
            document.getElementById('placeholder-text').style.display = 'none';

            try {
                // 1. Read file as base64
                const base64File = await toBase64(file);
                
                // 2. Upload to server
                const uploadRes = await fetch('/api/upload', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image: base64File })
                });
                const uploadData = await uploadRes.json();
                if (uploadData.status !== 'success') throw new Error(uploadData.message);
                uploadedGarmentUrl = uploadData.url;

                // 3. Auto Classify
                const classifyRes = await fetch('/api/classify', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ garment_url: uploadedGarmentUrl })
                });
                const classifyData = await classifyRes.json();
                if (classifyData.status !== 'success') throw new Error(classifyData.message);

                // Auto-fill form settings
                document.getElementById('garment_desc').value = classifyData.description || '';
                
                // Set category dropdown
                const category = classifyData.category || 'upper';
                if (category === 'lower') {
                    document.getElementById('sub_type').value = 'jeans';
                } else {
                    document.getElementById('sub_type').value = 'tshirt';
                }
                
                // Set gender
                setGender(classifyData.gender || 'male');

                // Enable config card
                const settingsSection = document.getElementById('settings-section');
                settingsSection.style.opacity = '1';
                settingsSection.style.pointerEvents = 'all';
                document.getElementById('generate-tryon-btn').disabled = false;

                // Hide overlay
                document.getElementById('status-overlay').style.display = 'none';
            } catch(e) {
                alert("Upload failed: " + e.message);
                document.getElementById('status-overlay').style.display = 'none';
                document.getElementById('placeholder-text').style.display = 'block';
            }
        }

        async function generateTryon() {
            // Disable buttons & show loading spinner
            document.getElementById('generate-tryon-btn').disabled = true;
            document.getElementById('tryon-spinner').style.display = 'block';
            document.getElementById('tryon-btn-text').innerText = "Generating Model...";

            document.getElementById('status-overlay').style.display = 'flex';
            document.getElementById('status-text').innerText = "Creating Photorealistic Model Image (Takes ~10 seconds)...";
            document.getElementById('result-image').style.display = 'none';
            document.getElementById('placeholder-text').style.display = 'none';

            const payload = {
                garment_url: uploadedGarmentUrl,
                gender: selectedGender,
                sub_type: document.getElementById('sub_type').value,
                description: document.getElementById('garment_desc').value
            };

            try {
                const res = await fetch('/api/tryon', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.status !== 'success') throw new Error(data.message);

                generatedModelUrl = data.url;

                // Display result image
                const resImg = document.getElementById('result-image');
                resImg.src = generatedModelUrl;
                resImg.style.display = 'block';

                document.getElementById('tryon-actions').style.display = 'flex';
                document.getElementById('status-overlay').style.display = 'none';
            } catch(e) {
                alert("Generation failed: " + e.message);
                document.getElementById('status-overlay').style.display = 'none';
                document.getElementById('placeholder-text').style.display = 'block';
            } finally {
                document.getElementById('generate-tryon-btn').disabled = false;
                document.getElementById('tryon-spinner').style.display = 'none';
                document.getElementById('tryon-btn-text').innerText = "Generate Try-On Model";
            }
        }

        async function generateVideo() {
            document.getElementById('generate-video-btn').disabled = true;
            document.getElementById('video-spinner').style.display = 'block';
            document.getElementById('video-btn-text').innerText = "Creating Video...";

            document.getElementById('status-overlay').style.display = 'flex';
            document.getElementById('status-text').innerText = "Rendering Catwalk Video (This takes 45-60 seconds)...";

            const payload = {
                image_url: generatedModelUrl,
                gender: selectedGender,
                sub_type: document.getElementById('sub_type').value
            };

            try {
                const res = await fetch('/api/video', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.status !== 'success') throw new Error(data.message);

                generatedVideoUrl = data.url;

                // Render video
                const resVideo = document.getElementById('result-video');
                resVideo.src = generatedVideoUrl;
                resVideo.style.display = 'block';
                document.getElementById('result-image').style.display = 'none'; // hide static

                document.getElementById('tryon-actions').style.display = 'none';
                document.getElementById('video-actions').style.display = 'flex';
                document.getElementById('status-overlay').style.display = 'none';
            } catch(e) {
                alert("Video generation failed: " + e.message);
                document.getElementById('status-overlay').style.display = 'none';
            } finally {
                document.getElementById('generate-video-btn').disabled = false;
                document.getElementById('video-spinner').style.display = 'none';
                document.getElementById('video-btn-text').innerText = "Generate Catwalk Video Reel";
            }
        }

        function downloadImage() {
            if (generatedModelUrl) window.open(generatedModelUrl, '_blank');
        }

        function downloadVideo() {
            if (generatedVideoUrl) window.open(generatedVideoUrl, '_blank');
        }

        function resetStudio() {
            uploadedGarmentUrl = "";
            generatedModelUrl = "";
            generatedVideoUrl = "";
            
            document.getElementById('garment-preview').style.display = 'none';
            document.getElementById('result-image').style.display = 'none';
            document.getElementById('result-video').style.display = 'none';
            
            document.getElementById('tryon-actions').style.display = 'none';
            document.getElementById('video-actions').style.display = 'none';
            document.getElementById('placeholder-text').style.display = 'block';
            document.getElementById('garment_desc').value = '';

            const settingsSection = document.getElementById('settings-section');
            settingsSection.style.opacity = '0.5';
            settingsSection.style.pointerEvents = 'none';
            document.getElementById('generate-tryon-btn').disabled = true;
        }

        const toBase64 = file => new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.readAsDataURL(file);
            reader.onload = () => resolve(reader.result);
            reader.onerror = error => reject(error);
        });
    </script>
</body>
</html>"""

class AdminPanelHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path in ['/', '/app']:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(APP_HTML.encode('utf-8'))
        elif self.path == '/admin':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(ADMIN_HTML.encode('utf-8'))
        elif self.path == '/api/config':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            config = load_config()
            self.wfile.write(json.dumps(config).encode('utf-8'))
        elif self.path == '/api/upload':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                req_data = json.loads(post_data.decode('utf-8'))
                b64_str = req_data.get("image")
                if "," in b64_str:
                    b64_str = b64_str.split(",")[1]
                image_bytes = base64.b64decode(b64_str)
                
                # Upload to Fal CDN
                uploaded_url = fal_client.upload(image_bytes, "image/jpeg")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "url": uploaded_url}).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
                
        elif self.path == '/api/classify':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                req_data = json.loads(post_data.decode('utf-8'))
                garment_url = req_data.get("garment_url")
                
                # Download garment bytes
                res = requests.get(garment_url)
                image_bytes = res.content
                
                loop = asyncio.new_event_loop()
                classification = loop.run_until_complete(classify_garment(image_bytes))
                loop.close()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "success",
                    "category": classification.get("category", "upper"),
                    "gender": classification.get("gender", "male"),
                    "description": classification.get("description", "")
                }).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
                
        elif self.path == '/api/tryon':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                req_data = json.loads(post_data.decode('utf-8'))
                garment_url = req_data.get("garment_url")
                gender = req_data.get("gender", "male")
                sub_type = req_data.get("sub_type", "shirt")
                garment_desc = req_data.get("description")
                
                loop = asyncio.new_event_loop()
                
                if not garment_desc:
                    # Download & classify
                    res = requests.get(garment_url)
                    image_bytes = res.content
                    classification = loop.run_until_complete(classify_garment(image_bytes))
                    garment_desc = classification.get("description", f"a premium fashion {sub_type}")
                
                # Tryon image generation
                tryon_url = loop.run_until_complete(run_dalle_generation(gender, sub_type, garment_desc))
                loop.close()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "success",
                    "url": tryon_url,
                    "description": garment_desc
                }).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
                
        elif self.path == '/api/video':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                req_data = json.loads(post_data.decode('utf-8'))
                image_url = req_data.get("image_url")
                gender = req_data.get("gender", "male")
                sub_type = req_data.get("sub_type", "shirt")
                
                loop = asyncio.new_event_loop()
                video_url = loop.run_until_complete(run_image_to_video(image_url, gender, sub_type))
                loop.close()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "url": video_url}).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
                
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/config':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                new_config = json.loads(post_data.decode('utf-8'))
                config = load_config()
                
                # Check if critical keys changed to trigger restart
                critical_keys = ["telegram_bot_token", "fal_key", "gemini_api_key", "openai_api_key"]
                keys_changed = False
                for key in critical_keys:
                    if new_config.get(key) != config.get(key):
                        keys_changed = True
                        break
                        
                config.update(new_config)
                save_config(config)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
                
                if keys_changed:
                    logger.info("Critical API keys modified. Restarting bot process...")
                    def restart():
                        import sys
                        import time
                        time.sleep(1)
                        os.execv(sys.executable, [sys.executable] + sys.argv)
                    threading.Thread(target=restart).start()
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/api/upload':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                req_data = json.loads(post_data.decode('utf-8'))
                b64_str = req_data.get("image")
                if "," in b64_str:
                    b64_str = b64_str.split(",")[1]
                image_bytes = base64.b64decode(b64_str)
                
                # Upload to Fal CDN
                uploaded_url = fal_client.upload(image_bytes, "image/jpeg")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "url": uploaded_url}).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
                
        elif self.path == '/api/classify':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                req_data = json.loads(post_data.decode('utf-8'))
                garment_url = req_data.get("garment_url")
                
                # Download garment bytes
                res = requests.get(garment_url)
                image_bytes = res.content
                
                loop = asyncio.new_event_loop()
                classification = loop.run_until_complete(classify_garment(image_bytes))
                loop.close()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "success",
                    "category": classification.get("category", "upper"),
                    "gender": classification.get("gender", "male"),
                    "description": classification.get("description", "")
                }).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
                
        elif self.path == '/api/tryon':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                req_data = json.loads(post_data.decode('utf-8'))
                garment_url = req_data.get("garment_url")
                gender = req_data.get("gender", "male")
                sub_type = req_data.get("sub_type", "shirt")
                garment_desc = req_data.get("description")
                
                loop = asyncio.new_event_loop()
                
                if not garment_desc:
                    # Download & classify
                    res = requests.get(garment_url)
                    image_bytes = res.content
                    classification = loop.run_until_complete(classify_garment(image_bytes))
                    garment_desc = classification.get("description", f"a premium fashion {sub_type}")
                
                # Tryon image generation
                tryon_url = loop.run_until_complete(run_dalle_generation(gender, sub_type, garment_desc))
                loop.close()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "success",
                    "url": tryon_url,
                    "description": garment_desc
                }).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
                
        elif self.path == '/api/video':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                req_data = json.loads(post_data.decode('utf-8'))
                image_url = req_data.get("image_url")
                gender = req_data.get("gender", "male")
                sub_type = req_data.get("sub_type", "shirt")
                
                loop = asyncio.new_event_loop()
                video_url = loop.run_until_complete(run_image_to_video(image_url, gender, sub_type))
                loop.close()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "url": video_url}).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
                
        else:
            self.send_response(404)
            self.end_headers()


import base64
from openai import OpenAI

# --- OpenAI Helpers ---
def get_openai_client():
    config = load_config()
    api_key = config.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise Exception("OpenAI API Key is missing! Please configure it in the Admin Web Panel.")
    return OpenAI(api_key=api_key)

async def classify_garment(image_bytes: bytes) -> dict:
    """Uses OpenAI GPT-4o with Vision to identify type, target gender, and write a detailed description."""
    try:
        client = get_openai_client()
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        prompt = (
            "Analyze the garment in this image and return a JSON object with three fields:\n"
            '- "category": Must be one of "upper" (shirts, t-shirts, jackets, tops), '
            '"lower" (jeans, pants, skirts, shorts), or "overall" (dresses, jumpsuits, full suits).\n'
            '- "gender": Must be one of "male", "female", or "unisex".\n'
            '- "description": A highly detailed and concise description of the garment. '
            'You MUST identify and clearly describe:\n'
            '1. The exact dominant color of the fabric (e.g., "dark chocolate brown", "navy blue", "pastel soft yellow"). '
            'Do NOT use dual or confusing color words (e.g., do NOT say "almost black", "blackish-brown", "charcoal-black" if the garment is brown, '
            'as this causes the image generator to render it black. Instead, specify the single dominant base color shade and tone clearly, like "dark espresso brown"). '
            'Also include a corresponding Hex color code (e.g. #3A2923).\n'
            '2. The exact fabric material and texture (e.g. rough matte linen, slubby textured linen, heavy rigid denim, fine knit, shiny silk/satin, cotton, etc.).\n'
            '3. Any logos, graphics, text, letters, symbols, or prints on the chest, pockets, or anywhere on the garment. '
            'You MUST explicitly state the exact text/letter (e.g., "an extremely tiny and small white embroidered \'V\' logo (about 1 cm tall) on the left chest" or "a red circular graphic print"), '
            'its exact color, its exact size (be extremely specific: e.g., state if it is "extremely small, tiny, subtle, about 1cm tall" or "large"), and its exact placement. '
            'If the logo is small, you MUST emphasize it as "extremely tiny, small, subtle" so the image generator does not make it too large.\n'
            '4. The fit, collar/neck type (e.g., polo collar, crew neck, V-neck), button design/color, pockets, stitching, and cuffs.\n'
            'This description will guide a text-to-image generator to replicate the garment exactly, so pay extreme attention to matching colors, logos/prints, and material properties. '
            'Do not mention the background.\n\n'
            "Only output the raw JSON object. Do not wrap in markdown code blocks."
        )
        
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=400
        )
        
        clean_text = response.choices[0].message.content.strip()
        data = json.loads(clean_text)
        logger.info(f"OpenAI Classification Result: {data}")
        return data
    except Exception as e:
        logger.error(f"Error in OpenAI classification: {e}")
        return {
            "category": "upper",
            "gender": "unisex",
            "description": "a premium plain fashion clothing item"
        }

async def generate_caption(category: str, gender: str) -> str:
    """Generates an engaging Instagram Reel caption with hashtags using OpenAI GPT-4o-mini."""
    try:
        client = get_openai_client()
        prompt = (
            f"Generate an engaging, short, high-converting Instagram caption for a fashion reel "
            f"showcasing a new {gender} {category} clothing item. "
            f"Include appropriate emojis and 5-8 relevant trending fashion hashtags. Keep it concise."
        )
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error generating caption: {e}")
        return "Upgrade your wardrobe with our latest collection! 👕✨ #Fashion #Style #NewCollection"


# Custom detailed prompts mapping for Male Models
CUSTOM_MALE_PROMPTS = {
    "shirt": {
        "prompt": "Create a realistic premium Italian male fashion model, athletic physique, tasteful arm tattoos, luxury fashion campaign look. The model must wear the EXACT shirt from the uploaded image. STRICTLY PRESERVE: exact fabric texture, exact color, exact print and pattern, exact stitching, exact collar shape, exact buttons, exact sleeve length, exact fit, exact branding. Do not redesign or alter any garment detail. Camera distance should show the model from mid-thigh to head so the entire shirt is clearly visible. Natural standing pose, relaxed confidence, luxury fashion catalog style, premium studio lighting, sharp focus, realistic skin texture, realistic shadows, high-end menswear photoshoot, ultra detailed fabric rendering, photorealistic, 8k quality. The shirt must be the primary focus of the image.",
        "negative_prompt": "cropped clothing, hidden garment, altered fabric, wrong color, wrong print, extra buttons, extra pockets, low quality fabric, blurry texture, unrealistic folds, oversized clothing, undersized clothing, duplicate garments, missing garment details, cartoon, illustration, CGI, low resolution, bad anatomy, distorted clothing, garment redesign"
    },
    "tshirt": {
        "prompt": "Create a realistic Italian male model with athletic build and subtle tattoos. The model must wear the EXACT t-shirt shown in the uploaded image. Preserve 100%: fabric texture, color, graphics, logos, prints, stitching, neckline, sleeve shape, fit. Do not modify any garment detail. Show model from mid-thigh to head. Luxury fashion campaign photography, premium menswear catalog, natural pose, realistic lighting, photorealistic skin, ultra sharp focus, highly detailed fabric texture, 8k quality. The t-shirt must remain the visual focus.",
        "negative_prompt": "cropped clothing, hidden garment, altered fabric, wrong color, wrong print, extra buttons, extra pockets, low quality fabric, blurry texture, unrealistic folds, oversized clothing, undersized clothing, duplicate garments, missing garment details, cartoon, illustration, CGI, low resolution, bad anatomy, distorted clothing, garment redesign"
    },
    "jeans": {
        "prompt": "Create a realistic Italian male model with athletic physique and tasteful tattoos. The model must wear the EXACT jeans from the uploaded image. Preserve: exact wash, exact fading, exact color, exact pockets, exact stitching, exact distressing, exact fit, exact length. Do not redesign any part of the jeans. Full body shot with slight camera distance so the entire jeans is clearly visible from waist to ankle. Luxury fashion catalog photography, premium studio lighting, realistic shadows, sharp fabric details, photorealistic, 8k quality. The jeans must be the primary focus.",
        "negative_prompt": "cropped clothing, hidden garment, altered fabric, wrong color, wrong print, extra buttons, extra pockets, low quality fabric, blurry texture, unrealistic folds, oversized clothing, undersized clothing, duplicate garments, missing garment details, cartoon, illustration, CGI, low resolution, bad anatomy, distorted clothing, garment redesign"
    },
    "cargo": {
        "prompt": "Create a realistic premium Italian male model with athletic build and tattoos. The model must wear the EXACT cargo pants shown in the uploaded image. Preserve: exact fabric, exact color, exact pocket placement, exact stitching, exact fit, exact length, exact design details. Do not modify the garment. Full body fashion photography with camera positioned slightly away so the entire cargo pants are clearly visible. Luxury streetwear campaign, realistic lighting, ultra detailed fabric rendering, photorealistic skin texture, premium catalog quality, 8k.",
        "negative_prompt": "cropped clothing, hidden garment, altered fabric, wrong color, wrong print, extra buttons, extra pockets, low quality fabric, blurry texture, unrealistic folds, oversized clothing, undersized clothing, duplicate garments, missing garment details, cartoon, illustration, CGI, low resolution, bad anatomy, distorted clothing, garment redesign"
    },
    "trouser": {
        "prompt": "Create a realistic Italian male fashion model with premium luxury look and subtle tattoos. The model must wear the EXACT trousers from the uploaded image. Preserve: exact color, exact fabric texture, exact crease lines, exact fit, exact stitching, exact waistband, exact pockets. Do not redesign the garment. Full body shot showing the entire trouser clearly from waist to ankle. Premium menswear campaign photography, luxury fashion brand quality, realistic lighting, clean background, photorealistic, ultra detailed, 8k quality.",
        "negative_prompt": "cropped clothing, hidden garment, altered fabric, wrong color, wrong print, extra buttons, extra pockets, low quality fabric, blurry texture, unrealistic folds, oversized clothing, undersized clothing, duplicate garments, missing garment details, cartoon, illustration, CGI, low resolution, bad anatomy, distorted clothing, garment redesign"
    },
    "shorts": {
        "prompt": "Create a realistic Italian male model with athletic physique and tasteful tattoos. The model must wear the EXACT shorts from the uploaded image. Preserve: exact fabric, exact color, exact pockets, exact stitching, exact length, exact fit. Do not modify any garment details. Show full body model standing naturally. Premium summer fashion photoshoot, realistic lighting, ultra sharp details, luxury catalog photography, photorealistic 8k quality. The shorts must be clearly visible and remain the focus of the image.",
        "negative_prompt": "cropped clothing, hidden garment, altered fabric, wrong color, wrong print, extra buttons, extra pockets, low quality fabric, blurry texture, unrealistic folds, oversized clothing, undersized clothing, duplicate garments, missing garment details, cartoon, illustration, CGI, low resolution, bad anatomy, distorted clothing, garment redesign"
    }
}

# --- Fal.ai Try-On Helper ---
async def run_virtual_try_on(garment_url: str, model_gender: str, cloth_type: str, sub_type: str = "shirt") -> str:
    """Calls Fal.ai Virtual Try-On depending on the RUN_MODE."""
    config = load_config()
    
    # Curated premium base model assets for realistic outputs
    male_models = [
        "https://fal.media/files/monkey/-LyhwXTRuc1nMzz26wUgR.png",
        "https://images.unsplash.com/photo-1618886614638-80e3c103d31a?auto=format&fit=crop&q=80&w=600",
        "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&q=80&w=600",
        "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&q=80&w=600"
    ]
    female_models = [
        "https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?auto=format&fit=crop&q=80&w=600",
        "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&q=80&w=600",
        "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=600",
        "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&q=80&w=600"
    ]
    
    # Pick a random model to make it look like different models are chosen
    if model_gender == "male":
        model_url = random.choice(male_models)
    else:
        model_url = random.choice(female_models)
    
    run_mode = config.get("run_mode", "premium").lower()
    
    # 1. Premium Mode (FASHN AI)
    if run_mode == "premium":
        # Map category names to FASHN API expectations
        category_map = {"upper": "tops", "lower": "bottoms", "overall": "one-pieces"}
        fashn_category = category_map.get(cloth_type, "tops")
        
        logger.info(f"Running Premium FASHN VTON: category={fashn_category}, model={model_url}, sub_type={sub_type}")
        
        arguments = {
            "model_image": model_url,
            "garment_image": garment_url,
            "category": fashn_category,
            "garment_photo_type": "auto",
            "mode": "quality"
        }
        
        result = await fal_client.run_async(
            "fal-ai/fashn/tryon/v1.6",
            arguments=arguments
        )
        return result["images"][0]["url"]
        
    # 2. Budget / Super Saver Mode (CatVTON)
    else:
        logger.info(f"Running CatVTON: cloth_type={cloth_type}, model={model_url}, sub_type={sub_type}")
        arguments = {
            "human_image_url": model_url,
            "garment_image_url": garment_url,
            "cloth_type": cloth_type
        }
        result = await fal_client.run_async(
            "fal-ai/cat-vton",
            arguments=arguments
        )
        return result["image"]["url"]


async def run_flux_generation(gender: str, sub_type: str, garment_desc: str) -> str:
    """Calls Fal.ai Flux/Dev to generate a photorealistic model wearing the described garment."""
    # Determine gender string for the prompt
    gender_str = "handsome Indian male model" if gender == "male" else "beautiful Indian female model"
    
    # Base prompt construction
    prompt = (
        f"A realistic premium {gender_str}, athletic physique, modeling {garment_desc}. "
        f"The model is standing confidently in a luxury minimalist studio setting with soft studio lighting. "
        f"Highly detailed fabric rendering, photorealistic skin texture, sharp focus, 8k resolution, "
        f"luxury fashion catalog style. The {sub_type} must be the primary focus of the image."
    )
    
    logger.info(f"Running Flux Image Generation: prompt='{prompt}'")
    
    arguments = {
        "prompt": prompt,
        "image_size": "portrait_16_9",
        "num_images": 1
    }
    
    result = await fal_client.run_async(
        "fal-ai/flux/dev",
        arguments=arguments
    )
    return result["images"][0]["url"]


async def run_dalle_generation(gender: str, sub_type: str, garment_desc: str) -> str:
    """Calls OpenAI DALL-E-3 to generate a photorealistic model wearing the described garment.
       Falls back to gpt-image-1 if dall-e-3 is not available on the key tier."""
    client = get_openai_client()
    config = load_config()
    
    # Get custom image prompt configurations from config
    prompt_group = "female_prompts" if gender == "female" else "male_prompts"
    custom_cfg = config.get(prompt_group, {}).get(sub_type, {})
    custom_prompt = custom_cfg.get("image_prompt", "")
    
    if not custom_prompt:
        gender_str = "handsome Indian male model" if gender == "male" else "beautiful Indian female model"
        custom_prompt = (
            f"A photorealistic studio fashion portrait of a premium {gender_str}, athletic build, "
            f"modeling [GARMENT_DESCRIPTION]. The model is standing confidently in a luxury clean minimalist studio setting "
            f"with high-end soft studio lighting. High-fashion brand catalog style. Crisp details on the {sub_type}. "
            f"The clothing fabric, color, and design must look extremely premium, clean and detailed."
        )
        
    prompt = custom_prompt.replace("[GARMENT_DESCRIPTION]", garment_desc)
    
    dalle_err = None
    # Try DALL-E-3 first
    try:
        logger.info(f"Attempting OpenAI DALL-E 3 Image Generation: prompt='{prompt}'")
        response = await asyncio.to_thread(
            client.images.generate,
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size="1024x1792", # Vertical Reels aspect ratio format for DALL-E 3
            quality="standard"
        )
        if response.data[0].url:
            return response.data[0].url
    except Exception as e:
        dalle_err = e
        logger.warning(f"DALL-E 3 failed: {dalle_err}. Falling back to gpt-image-1...")
        
    # Fallback to gpt-image-1 if DALL-E-3 fails
    try:
        logger.info(f"Running fallback gpt-image-1 Image Generation: prompt='{prompt}'")
        response = await asyncio.to_thread(
            client.images.generate,
            model="gpt-image-1",
            prompt=prompt,
            n=1,
            size="1024x1536"
        )
        
        # Check if URL or base64 is returned
        item = response.data[0]
        if getattr(item, "url", None):
            return item.url
            
        b64_data = getattr(item, "b64_json", None)
        if b64_data:
            import base64
            image_bytes = base64.b64decode(b64_data)
            
            # Make sure FAL_KEY is loaded in environment for fal_client to upload
            fal_key = config.get("fal_key") or os.getenv("FAL_KEY")
            if fal_key:
                os.environ["FAL_KEY"] = fal_key
                
            logger.info("Uploading base64 generated image to Fal.ai CDN...")
            uploaded_url = await asyncio.to_thread(
                fal_client.upload,
                image_bytes,
                "image/png"
            )
            logger.info(f"Fal.ai CDN Upload successful: {uploaded_url}")
            return uploaded_url
            
        raise Exception("gpt-image-1 did not return url or b64_json data.")
    except Exception as fallback_err:
        logger.error(f"Fallback gpt-image-1 failed: {fallback_err}")
        raise Exception(f"OpenAI Image Generation failed. DALL-E 3 Error: {dalle_err}. Fallback Error: {fallback_err}")


# --- Fal.ai Image-to-Video Helper ---
async def run_image_to_video(image_url: str, gender: str = "male", sub_type: str = "shirt") -> str:
    """Calls Fal.ai Image-to-Video API based on the RUN_MODE, using specific sub_type prompt configurations."""
    config = load_config()
    
    # Get custom prompt configurations from config
    prompt_group = "female_prompts" if gender == "female" else "male_prompts"
    custom_cfg = config.get(prompt_group, {}).get(sub_type, {})
    if not custom_cfg:
        custom_cfg = CUSTOM_MALE_PROMPTS.get(sub_type, CUSTOM_MALE_PROMPTS["shirt"])
        
    custom_prompt = custom_cfg.get("prompt", "")
    custom_neg = custom_cfg.get("negative_prompt", "")
    
    run_mode = config.get("run_mode", "premium").lower()
    
    # Append slow motion helper text if enabled in configuration
    if config.get("video_slow_motion", False):
        custom_prompt = custom_prompt.strip()
        if not custom_prompt.endswith("."):
            custom_prompt += "."
        custom_prompt += " Slow motion catwalk movements, elegant slow-mo, smooth fabric physics, slow tempo movement, cinematic flow."

    # 1. Premium Mode (Kling AI Pro)
    if run_mode == "premium":
        logger.info(f"Running Kling Video (Premium Mode) for sub_type={sub_type}...")
        duration = int(config.get("video_duration", 5))
        arguments = {
            "image_url": image_url,
            "prompt": custom_prompt,
            "negative_prompt": custom_neg,
            "aspect_ratio": "9:16",
            "duration": duration
        }
        result = await fal_client.run_async(
            "fal-ai/kling-video/v1.5/pro/image-to-video",
            arguments=arguments
        )
        return result["video"]["url"]
        
    # 2. Super Saver Mode (Stable Video Diffusion)
    elif run_mode == "supersaver":
        logger.info("Running Stable Video Diffusion (Super Saver Mode)...")
        arguments = {
            "image_url": image_url,
            "motion_bucket_id": 127
        }
        result = await fal_client.run_async(
            "fal-ai/stable-video-diffusion",
            arguments=arguments
        )
        return result["video"]["url"]
        
    # 3. Budget Mode (Wan 2.1 Image-to-Video) - DEFAULT
    else:
        logger.info(f"Running Wan 2.1 Video (Budget Mode) for sub_type={sub_type}...")
        arguments = {
            "image_url": image_url,
            "prompt": custom_prompt,
            "aspect_ratio": "9:16"
        }
        result = await fal_client.run_async(
            "fal-ai/wan-i2v",
            arguments=arguments
        )
        return result["video"]["url"]


# --- Instagram Graph API Publisher ---
async def publish_to_instagram(video_url: str, caption: str) -> str:
    """Publishes a Reel to Instagram and returns the permalink."""
    config = load_config()
    skip_post = config.get("skip_instagram_post", True)
    
    if skip_post:
        return "Bypassed (SKIP_INSTAGRAM_POST=True)"
        
    insta_id = config.get("instagram_business_account_id", "")
    access_token = config.get("meta_access_token", "")
    
    try:
        # Phase 1: Create Media Container
        logger.info("Creating Instagram Media Container...")
        container_url = f"https://graph.facebook.com/v20.0/{insta_id}/media"
        container_data = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": access_token
        }
        
        response = await asyncio.to_thread(requests.post, container_url, data=container_data)
        res_json = response.json()
        
        if "id" not in res_json:
            raise Exception(f"Failed to create media container: {res_json}")
            
        container_id = res_json["id"]
        logger.info(f"Container Created successfully! ID: {container_id}")
        
        # Phase 2: Poll Container Status (Reels take time to process)
        status_url = f"https://graph.facebook.com/v20.0/{container_id}"
        status_params = {
            "fields": "status_code,status",
            "access_token": access_token
        }
        
        logger.info("Waiting for video to be processed by Meta...")
        for attempt in range(15):  # Poll up to 15 times (approx 2.5 minutes)
            await asyncio.sleep(10)
            status_res = await asyncio.to_thread(requests.get, status_url, params=status_params)
            status_json = status_res.json()
            logger.info(f"Poll attempt {attempt+1}: {status_json}")
            
            if status_json.get("status_code") == "FINISHED":
                break
            elif status_json.get("status_code") == "ERROR":
                raise Exception(f"Meta video processing failed: {status_json}")
        else:
            raise Exception("Timeout waiting for Instagram video processing.")
            
        # Phase 3: Publish Media
        logger.info("Publishing Reel...")
        publish_url = f"https://graph.facebook.com/v20.0/{insta_id}/media_publish"
        publish_data = {
            "creation_id": container_id,
            "access_token": access_token
        }
        
        publish_res = await asyncio.to_thread(requests.post, publish_url, data=publish_data)
        pub_json = publish_res.json()
        
        if "id" not in pub_json:
            raise Exception(f"Failed to publish media: {pub_json}")
            
        post_id = pub_json["id"]
        logger.info(f"Published successfully! Post ID: {post_id}")
        
        # Get permalink
        info_url = f"https://graph.facebook.com/v20.0/{post_id}"
        info_params = {
            "fields": "permalink",
            "access_token": access_token
        }
        info_res = await asyncio.to_thread(requests.get, info_url, params=info_params)
        return info_res.json().get("permalink", f"https://www.instagram.com/p/{post_id}/")
        
    except Exception as e:
        logger.error(f"Instagram Post Error: {e}")
        raise e


# --- Telegram Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends welcome message."""
    config = load_config()
    run_mode = config.get("run_mode", "premium").upper()
    skip_post = config.get("skip_instagram_post", True)
    
    welcome_text = config.get("telegram_start_text", "").strip()
    if not welcome_text:
        welcome_text = (
            "👋 Welcome to the AI Fashion Try-On & Reels Bot!\n\n"
            f"⚡ Current Mode: *{run_mode}*\n"
            f"📸 Instagram Auto-Publish: *{'Disabled (Test Mode)' if skip_post else 'Enabled'}*\n\n"
            "How to use:\n"
            "1. Send me a photo of any clothing item (flat-lay or on a hanger).\n"
            "2. The AI will automatically detect if it is for a Male or Female model!\n"
            "3. Select the garment type if prompted (Shirt, T-Shirt, Jeans, Cargo, Trouser, Shorts).\n"
            "4. The AI will render the garment onto the correct model using your custom settings!\n"
            "5. Click the button to automatically generate a video reel and post it to Instagram!"
        )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# --- Main Photo Handling & VTON Pipeline ---
async def handle_incoming_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes the uploaded photo, runs Gemini detection, and triggers sub-garment selection."""
    msg = await update.message.reply_text("🔍 Analyzing clothing item...")
    
    try:
        # Get image bytes
        photo_file = await update.message.photo[-1].get_file()
        photo_byte_array = await photo_file.download_as_bytearray()
        image_bytes = bytes(photo_byte_array)
        
        # Store in user session state
        context.user_data["image_bytes"] = image_bytes
        
        # 1. Gemini Auto-Classification
        classification = await classify_garment(image_bytes)
        category = classification.get("category", "upper")
        classified_gender = classification.get("gender", "male").lower()
        
        # Map unisex to male
        gender = "male" if classified_gender in ["male", "unisex"] else "female"
        context.user_data["gender"] = gender
        context.user_data["garment_description"] = classification.get("description", "a premium casual clothing item")
        
        await msg.delete()
        
        gender_upper = gender.upper()
        config = load_config()
        default_upper = config.get("default_upper_category", "ask").lower()
        default_lower = config.get("default_lower_category", "ask").lower()

        if category == "upper":
            if default_upper in ["shirt", "tshirt"]:
                context.user_data["sub_type"] = default_upper
                context.user_data["category"] = "upper"
                status_msg = await update.message.reply_text(f"✨ Generating Try-On Image on {gender_upper} Model using strict *{default_upper.upper()}* prompt settings...")
                await trigger_try_on_flow(update, context, status_msg)
            else:
                # Options for top
                keyboard = [
                    [
                        InlineKeyboardButton("👕 Shirt", callback_data="sub_shirt"),
                        InlineKeyboardButton("👕 T-Shirt", callback_data="sub_tshirt")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"👕 Top clothing detected! Choose type to apply {gender_upper} model prompts:",
                    reply_markup=reply_markup
                )
        elif category == "lower":
            if default_lower in ["jeans", "cargo", "trouser", "shorts"]:
                context.user_data["sub_type"] = default_lower
                context.user_data["category"] = "lower"
                status_msg = await update.message.reply_text(f"✨ Generating Try-On Image on {gender_upper} Model using strict *{default_lower.upper()}* prompt settings...")
                await trigger_try_on_flow(update, context, status_msg)
            else:
                # Options for bottom
                keyboard = [
                    [
                        InlineKeyboardButton("👖 Jeans", callback_data="sub_jeans"),
                        InlineKeyboardButton("👖 Cargo Pants", callback_data="sub_cargo")
                    ],
                    [
                        InlineKeyboardButton("👖 Trouser", callback_data="sub_trouser"),
                        InlineKeyboardButton("🩳 Shorts", callback_data="sub_shorts")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"👖 Bottom clothing detected! Choose type to apply {gender_upper} model prompts:",
                    reply_markup=reply_markup
                )
        else:
            # Overall or default fallback
            context.user_data["sub_type"] = "shirt"
            context.user_data["category"] = "upper"
            status_msg = await update.message.reply_text(f"✨ Generating Try-On Image on {gender_upper} Model...")
            await trigger_try_on_flow(update, context, status_msg)
            
    except Exception as e:
        logger.error(f"Error handling incoming photo: {e}")
        await update.message.reply_text("❌ Failed to process image. Please try again with a clear photo.")



async def trigger_try_on_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, status_msg):
    """Generates a model wearing the garment using OpenAI DALL-E-3."""
    try:
        gender = context.user_data.get("gender", "male")
        category = context.user_data.get("category", "upper")
        sub_type = context.user_data.get("sub_type", "shirt")
        garment_desc = context.user_data.get("garment_description", f"a premium fashion {sub_type}")
        
        # Run OpenAI DALL-E-3 Image generation
        logger.info(f"Generating image via OpenAI DALL-E-3: gender={gender}, sub_type={sub_type}")
        tryon_url = await run_dalle_generation(gender, sub_type, garment_desc)
        context.user_data["tryon_image_url"] = tryon_url
        
        # Send Try-On result to Telegram
        keyboard = [
            [InlineKeyboardButton("🎬 Make Video Reel & Post", callback_data="generate_video")],
            [InlineKeyboardButton("📸 Try Another Garment", callback_data="reset")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_msg.delete()
        
        # Send generated photo with buttons
        await update.message.reply_photo(
            photo=tryon_url,
            caption=(
                f"✅ Premium Model Image generated!\n"
                f"• Category: {category.upper()} ({sub_type.upper()})\n"
                f"• Model: {gender.upper()} (OpenAI DALL-E-3 Mode)"
            ),
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"DALL-E Flow failed: {e}")
        await status_msg.edit_text(f"❌ OpenAI DALL-E image generation failed. Error: {e}")


# --- Shared Video Generation Flow ---
async def trigger_video_flow(chat_id: int, context: ContextTypes.DEFAULT_TYPE, status_msg):
    """Performs video generation, caption generation, and Instagram publishing."""
    tryon_image_url = context.user_data.get("tryon_image_url")
    if not tryon_image_url:
        await context.bot.send_message(chat_id=chat_id, text="❌ No try-on photo found. Please upload a new clothing photo first.")
        return
        
    try:
        sub_type = context.user_data.get("sub_type", "shirt")
        gender = context.user_data.get("gender", "male")
        # Step A: Image-to-Video using custom sub_type prompts
        video_url = await run_image_to_video(tryon_image_url, gender, sub_type)
        logger.info(f"Video generated successfully: {video_url}")
        
        # Step B: Caption Generation
        category = context.user_data.get("category", "upper")
        gender = context.user_data.get("gender", "male")
        caption = await generate_caption(category, gender)
        
        # Step C: Instagram Auto-Post
        config = load_config()
        run_mode_str = config.get("run_mode", "premium").upper()
        skip_post = config.get("skip_instagram_post", True)
        
        if skip_post:
            await status_msg.delete()
            # If skipping, just send the video to user on Telegram!
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_url,
                caption=f"✅ Reel Video generated successfully ({run_mode_str} Mode)!\n\n*Generated Caption:*\n{caption}\n\n_(Instagram posting was bypassed)_",
                parse_mode="Markdown"
            )
        else:
            await status_msg.edit_text("🚀 Uploading video and posting to Instagram Reels...")
            insta_link = await publish_to_instagram(video_url, caption)
            
            # Notify User of Success with link
            await status_msg.delete()
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_url,
                caption=(
                    f"🎉 **Successfully Posted to Instagram!**\n\n"
                    f"🔗 [View Instagram Post]({insta_link})\n\n"
                    f"*Caption used:*\n{caption}"
                ),
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"Reel generation flow failed: {e}")
        await status_msg.edit_text(f"❌ Failed to create video. Error: {e}")


# --- Callback Button Handlers (Interactive actions) ---
async def handle_callback_queries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes button clicks (subcategory selection, video generation, reset)."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    logger.info(f"Callback Query received: {data}")
    
    # 1. Subcategory Selection
    if data.startswith("sub_"):
        sub_type = data.split("_")[1] # e.g. shirt, tshirt, jeans, cargo, trouser, shorts
        context.user_data["sub_type"] = sub_type
        
        # Auto-detect category based on sub_type
        if sub_type in ["shirt", "tshirt"]:
            context.user_data["category"] = "upper"
        else:
            context.user_data["category"] = "lower"
            
        gender = context.user_data.get("gender", "male")
        status_msg = await query.message.reply_text(f"✨ Generating Try-On Image on {gender.upper()} Model using strict *{sub_type.upper()}* prompt settings...")
        await query.message.delete()
        
        # Run try-on flow
        await trigger_try_on_flow(query, context, status_msg)
        
    # 2. Video Reel Generation & Posting
    elif data == "generate_video":
        status_msg = await query.message.reply_text("🎬 Generating Video Reel (This takes about 45-60 seconds)...")
        await query.message.delete()
        await trigger_video_flow(query.message.chat_id, context, status_msg)
            
    # 3. Reset Flow
    elif data == "reset":
        context.user_data.clear()
        await query.message.delete()
        await query.message.reply_text("📸 Send me a new clothing photo to start.")


# --- Text Message Handler (Fallback for browser inline button issues) ---
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes typed text commands in case inline buttons do not work on user's client."""
    text = update.message.text.lower().strip()
    logger.info(f"Text message received: '{text}'")
    
    image_bytes = context.user_data.get("image_bytes")
    if not image_bytes:
        await update.message.reply_text("📸 Please send a clothing photo first!")
        return
        
    # 1. Model Subcategory Text Match
    matched_sub = None
    if "t-shirt" in text or "tshirt" in text or "tees" in text:
        matched_sub = "tshirt"
        context.user_data["category"] = "upper"
    elif "shirt" in text:
        matched_sub = "shirt"
        context.user_data["category"] = "upper"
    elif "jeans" in text or "denim" in text:
        matched_sub = "jeans"
        context.user_data["category"] = "lower"
    elif "cargo" in text:
        matched_sub = "cargo"
        context.user_data["category"] = "lower"
    elif "trouser" in text or "pant" in text:
        matched_sub = "trouser"
        context.user_data["category"] = "lower"
    elif "shorts" in text or "half pant" in text:
        matched_sub = "shorts"
        context.user_data["category"] = "lower"
        
    if matched_sub:
        context.user_data["sub_type"] = matched_sub
        gender = context.user_data.get("gender", "male")
        status_msg = await update.message.reply_text(f"✨ Generating Try-On Image on {gender.upper()} Model using strict *{matched_sub.upper()}* prompt settings...")
        await trigger_try_on_flow(update, context, status_msg)
        return
        
    # 2. Video Reel Text Match
    if "video" in text or "reel" in text or "make" in text or "post" in text or "🎬" in text:
        tryon_image_url = context.user_data.get("tryon_image_url")
        if not tryon_image_url:
            await update.message.reply_text("❌ No try-on photo found. Please select a clothing subcategory first.")
            return
        status_msg = await update.message.reply_text("🎬 Generating Video Reel (This takes about 45-60 seconds)...")
        await trigger_video_flow(update.message.chat_id, context, status_msg)
        
    # 3. Reset / New Photo Match
    elif "reset" in text or "another" in text or "start over" in text:
        context.user_data.clear()
        await update.message.reply_text("📸 Send me a new clothing photo to start.")
        
    # 4. Fallback Help Text
    else:
        await update.message.reply_text(
            "❓ Send me a *photo* of a garment to start.\n\n"
            "If a photo is already uploaded, you can choose options by typing:\n"
            "• *shirt* or *t-shirt* (for tops)\n"
            "• *jeans*, *cargo*, *trouser*, or *shorts* (for bottoms)\n"
            "• Type *'make video'* to generate the reel.\n"
            "• Type *'reset'* to clear history.",
            parse_mode="Markdown"
        )


# --- Main Webhook / Polling Orchestrator ---
def main():
    logger.info("Initializing Bot Services...")
    
    # Start Telegram Bot in a background thread so it doesn't block the VTON Web App if Telegram is down
    def run_telegram_bot():
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.strip() == "":
            logger.warning("No Telegram Bot Token provided. Telegram integration is disabled.")
            return
            
        try:
            logger.info("Starting Telegram Bot thread...")
            # Create a separate event loop for the background thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(MessageHandler(filters.PHOTO, handle_incoming_photo))
            application.add_handler(CallbackQueryHandler(handle_callback_queries))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
            
            logger.info("Running Telegram polling (background thread)...")
            application.run_polling(close_loop=False, stop_signals=None)
        except Exception as e:
            logger.error(f"Telegram Bot failed to start (possibly blocked by ISP or timeout): {e}")
            logger.info("Telegram integration bypassed. Running Web VTON App only.")

    # Start bot thread if token is present
    if TELEGRAM_BOT_TOKEN:
        threading.Thread(target=run_telegram_bot, daemon=True).start()
    else:
        logger.info("Bypassing Telegram Bot. Only running Web App.")

    # Start the Web App Server on the main thread
    port_str = os.environ.get("PORT")
    port = int(port_str) if port_str else 5000
    server_address = ('', port)
    try:
        httpd = http.server.HTTPServer(server_address, AdminPanelHandler)
        logger.info(f"VTON Studio Web Server started at http://localhost:{port}")
        httpd.serve_forever()
    except Exception as e:
        logger.error(f"Failed to start VTON Web Server: {e}")


if __name__ == "__main__":
    main()
