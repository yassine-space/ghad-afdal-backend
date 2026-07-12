"""
Django settings for config project.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-u1xwq@jsz*53zk826p6-+54-8%w_(8g22vgoa9$sx%l&8&^db8')
DEBUG = os.getenv("DEBUG", "False") == "True"
IS_DEBUG = DEBUG
ALLOW_LAN_TESTING = os.getenv("ALLOW_LAN_TESTING", "True") == "True"
CSRF_TRUSTED_ORIGINS = [
    'https://ghad-afdal-frontend.vercel.app',
    'https://ghad-afdal-api.onrender.com',
]

if IS_DEBUG or ALLOW_LAN_TESTING:
    CSRF_TRUSTED_ORIGINS += [
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ]

ALLOWED_HOSTS = [
    "ghad-afdal-api.onrender.com",
    "localhost",
    "127.0.0.1",
]

if IS_DEBUG or ALLOW_LAN_TESTING:
    ALLOWED_HOSTS += ['*']
# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',  
    'ghadapi',
    'rest_framework_simplejwt',
    "storages",
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # This MUST be at the top
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'ghadapi.middleware.UpdateLastActivityMiddleware',  # Custom middleware to update last activity
]

# CORS Settings - ADD THIS SECTION
CORS_ALLOW_ALL_ORIGINS = False  # For development only


# Allow credentials (cookies, authorization headers)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    "https://ghad-afdal.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

if IS_DEBUG or ALLOW_LAN_TESTING:
    CORS_ALLOW_ALL_ORIGINS = True
# Allow all methods
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

# Allow all headers
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# Rest of your settings...
ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
WSGI_APPLICATION = 'config.wsgi.application'

# Database


STATIC_URL = "static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")


import os
import dj_database_url

if os.getenv("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.config(
            default=os.getenv("DATABASE_URL")
        )
    }
else:
    # 🖥️ Local development
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT"),
        }
    }



# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
AUTH_USER_MODEL = 'ghadapi.User'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

from datetime import timedelta

SIMPLE_JWT = {
    # Access token: 8 hours — covers a full work day without re-login
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    # Refresh token: 30 days — allows silent refresh for regular users
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    # Issue a new refresh token on every refresh call, resetting the 30-day window
    'ROTATE_REFRESH_TOKENS': True,
    # Blacklist old refresh tokens after rotation (requires 'rest_framework_simplejwt.token_blacklist' in INSTALLED_APPS)
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,
}
CORS_EXPOSE_HEADERS = [
    'Content-Type',
    'X-CSRFToken',
    'Authorization',
    'X-Missing-Ids']

# ─────────────────────────────────────────────
# MEDIA / FILE STORAGE
# Local dev  → files saved to disk at MEDIA_ROOT, served by Django (DEBUG=True)
# Production → files saved to Cloudflare R2 (S3-compatible), served via public R2 URL
# Toggle is controlled by USE_R2 env var (set it to True on Render only).
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# MEDIA / FILE STORAGE
# ─────────────────────────────────────────────

USE_R2 = os.getenv("USE_R2", "False") == "True"

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

if USE_R2:
    AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
    AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
    AWS_S3_ENDPOINT_URL = os.environ["AWS_S3_ENDPOINT_URL"]
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "auto")
    AWS_S3_CUSTOM_DOMAIN = os.environ["AWS_S3_CUSTOM_DOMAIN"]  # e.g. pub-xxxx.r2.dev — no scheme, no trailing slash

    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_SIGNATURE_VERSION = "s3v4"

    MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"

    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
# else: no STORAGES override → Django uses its built-in FileSystemStorage,
# saving to MEDIA_ROOT and serving from MEDIA_URL, exactly like local dev.