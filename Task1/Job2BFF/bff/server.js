const express = require('express');
const session = require('express-session');
const cors = require('cors');
const axios = require('axios');
const crypto = require('crypto');

const app = express();

const PORT = process.env.PORT || 8000;
const KEYCLOAK_INTERNAL_URL = process.env.KEYCLOAK_INTERNAL_URL || 'http://keycloak:8080';
const KEYCLOAK_PUBLIC_URL = process.env.KEYCLOAK_PUBLIC_URL || 'http://localhost:8080';
const REALM = process.env.REALM || 'reports-realm';
const CLIENT_ID = process.env.CLIENT_ID || 'reports-bff';
const CLIENT_SECRET = process.env.CLIENT_SECRET || 'bff-secret-change-me';
const REDIRECT_URI = process.env.REDIRECT_URI || 'http://localhost:8000/auth/callback';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3000';
const SESSION_SECRET = process.env.SESSION_SECRET || 'change-me';

app.use(cors({
  origin: FRONTEND_URL,
  credentials: true,
}));

app.use(express.json());

app.use(session({
  secret: SESSION_SECRET,
  resave: false,
  saveUninitialized: false,
  cookie: {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    maxAge: 1000 * 60 * 60 * 8,
  },
}));

function base64url(buffer) {
  return buffer
    .toString('base64')
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
}

function sha256(str) {
  return crypto.createHash('sha256').update(str).digest();
}

function decodeJwt(token) {
  const payload = token.split('.')[1];
  return JSON.parse(Buffer.from(payload, 'base64').toString('utf8'));
}

function tokenUrl() {
  return `${KEYCLOAK_INTERNAL_URL}/realms/${REALM}/protocol/openid-connect/token`;
}

async function refreshTokens(session) {
  const tokens = session.tokens;

  if (tokens.expires_at && tokens.expires_at > Math.floor(Date.now() / 1000) + 30) {
    return tokens.access_token;
  }

  if (!tokens.refresh_token) {
    throw new Error('No refresh token');
  }

  const params = new URLSearchParams({
    grant_type: 'refresh_token',
    refresh_token: tokens.refresh_token,
    client_id: CLIENT_ID,
    client_secret: CLIENT_SECRET,
  });

  const response = await axios.post(tokenUrl(), params.toString(), {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });

  session.tokens = {
    ...tokens,
    ...response.data,
    expires_at: Math.floor(Date.now() / 1000) + (response.data.expires_in || 300),
  };

  return session.tokens.access_token;
}

app.get('/health', (req, res) => {
  res.json({ ok: true });
});

app.get('/auth/login', (req, res) => {
  const state = base64url(crypto.randomBytes(32));
  const codeVerifier = base64url(crypto.randomBytes(32));
  const codeChallenge = base64url(sha256(codeVerifier));

  req.session.state = state;
  req.session.codeVerifier = codeVerifier;
  req.session.redirectTo = req.query.redirect_uri || FRONTEND_URL;

  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    response_type: 'code',
    scope: 'openid profile email',
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
  });

  res.redirect(
    `${KEYCLOAK_PUBLIC_URL}/realms/${REALM}/protocol/openid-connect/auth?${params.toString()}`
  );
});

app.get('/auth/callback', async (req, res) => {
  const { code, state } = req.query;

  if (!code || !state || state !== req.session.state) {
    return res.status(400).send('Invalid state');
  }

  try {
    const params = new URLSearchParams({
      grant_type: 'authorization_code',
      code,
      redirect_uri: REDIRECT_URI,
      client_id: CLIENT_ID,
      client_secret: CLIENT_SECRET,
      code_verifier: req.session.codeVerifier,
    });

    const response = await axios.post(tokenUrl(), params.toString(), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });

    const tokens = response.data;
    tokens.expires_at = Math.floor(Date.now() / 1000) + (tokens.expires_in || 300);

    req.session.tokens = tokens;
    req.session.user = tokens.id_token ? decodeJwt(tokens.id_token) : { sub: 'unknown' };

    delete req.session.codeVerifier;
    delete req.session.state;

    res.redirect(req.session.redirectTo || FRONTEND_URL);
  } catch (err) {
    console.error('Token exchange failed:', err.response?.data || err.message);
    res.status(500).send('Token exchange failed');
  }
});

app.get('/auth/me', (req, res) => {
  if (!req.session.user) {
    return res.status(401).json({ authenticated: false });
  }

  res.json({
    authenticated: true,
    user: req.session.user,
  });
});

app.post('/auth/logout', (req, res) => {
  req.session.destroy(() => {
    res.clearCookie('connect.sid');
    res.json({ ok: true });
  });
});

app.get('/api/reports', async (req, res) => {
  if (!req.session.tokens) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  try {
    const accessToken = await refreshTokens(req.session);

    if (process.env.REPORTS_API_URL) {
      const apiRes = await axios.get(`${process.env.REPORTS_API_URL}/reports`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      return res.json(apiRes.data);
    }

    res.json({
      reports: [
        {
          id: 1,
          name: 'Usage Report',
          generatedAt: new Date().toISOString(),
        },
      ],
    });
  } catch (err) {
    console.error('Reports error:', err.message);
    res.status(401).json({ error: 'Unauthorized' });
  }
});

app.listen(PORT, () => {
  console.log(`BFF listening on ${PORT}`);
});