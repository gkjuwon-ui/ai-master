import crypto from 'crypto';

const ALGORITHM = 'aes-256-gcm';
const IV_LENGTH = 16;
const SALT_LENGTH = 64;
const TAG_LENGTH = 16;
const KEY_LENGTH = 32;
const ITERATIONS = 100000;

const getKey = (salt: Buffer): Buffer => {
  const secret = process.env.ENCRYPTION_KEY || process.env.JWT_SECRET || 'dev-secret-change-me';
  if (secret === 'dev-secret-change-me' && process.env.NODE_ENV === 'production') {
    throw new Error('FATAL: ENCRYPTION_KEY must be set in production. Refusing to use dev defaults for encryption.');
  }
  return crypto.pbkdf2Sync(secret, salt, ITERATIONS, KEY_LENGTH, 'sha512');
};

export function encrypt(plaintext: string): string {
  const salt = crypto.randomBytes(SALT_LENGTH);
  const iv = crypto.randomBytes(IV_LENGTH);
  const key = getKey(salt);
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv);

  let encrypted = cipher.update(plaintext, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  const tag = cipher.getAuthTag();

  return Buffer.concat([
    salt,
    iv,
    tag,
    Buffer.from(encrypted, 'hex'),
  ]).toString('base64');
}

export function decrypt(ciphertext: string): string {
  const buffer = Buffer.from(ciphertext, 'base64');

  const salt = buffer.subarray(0, SALT_LENGTH);
  const iv = buffer.subarray(SALT_LENGTH, SALT_LENGTH + IV_LENGTH);
  const tag = buffer.subarray(SALT_LENGTH + IV_LENGTH, SALT_LENGTH + IV_LENGTH + TAG_LENGTH);
  const encrypted = buffer.subarray(SALT_LENGTH + IV_LENGTH + TAG_LENGTH);

  const key = getKey(salt);
  const decipher = crypto.createDecipheriv(ALGORITHM, key, iv);
  decipher.setAuthTag(tag);

  let decrypted = decipher.update(encrypted.toString('hex'), 'hex', 'utf8');
  decrypted += decipher.final('utf8');

  return decrypted;
}

export function generateApiKey(): { key: string; hash: string; prefix: string } {
  const key = `ap_${crypto.randomBytes(32).toString('hex')}`;
  const hash = crypto.createHash('sha256').update(key).digest('hex');
  const prefix = key.substring(0, 11);
  return { key, hash, prefix };
}

export function hashApiKey(key: string): string {
  return crypto.createHash('sha256').update(key).digest('hex');
}

export function generateLicenseKey(): string {
  const segments = Array.from({ length: 4 }, () =>
    crypto.randomBytes(4).toString('hex').toUpperCase()
  );
  return segments.join('-');
}
