import nodemailer from 'nodemailer';
import { config } from '../config';
import { logger } from '../utils/logger';

class EmailService {
  private transporter: nodemailer.Transporter | null = null;

  private getTransporter(): nodemailer.Transporter {
    if (!this.transporter) {
      if (!config.smtp.user || !config.smtp.pass) {
        logger.warn('SMTP credentials not configured. Emails will be logged to console only.');
        // Create a test/console transporter for development
        this.transporter = nodemailer.createTransport({
          streamTransport: true,
          newline: 'unix',
        });
      } else {
        this.transporter = nodemailer.createTransport({
          host: config.smtp.host,
          port: config.smtp.port,
          secure: config.smtp.secure,
          auth: {
            user: config.smtp.user,
            pass: config.smtp.pass,
          },
        });
      }
    }
    return this.transporter;
  }

  async sendVerificationEmail(to: string, code: string, displayName: string): Promise<boolean> {
    const subject = '[OGENTI] Email Verification Code';

    const html = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin:0;padding:0;background:#000;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
      <div style="max-width:480px;margin:40px auto;padding:40px 32px;background:#0a0a0a;border:1px solid rgba(255,255,255,0.08);border-radius:16px;">
        <!-- Logo -->
        <div style="text-align:center;margin-bottom:32px;">
          <span style="font-size:28px;font-weight:700;color:#fff;letter-spacing:-0.02em;">OGENTI</span>
        </div>

        <!-- Greeting -->
        <p style="color:rgba(255,255,255,0.7);font-size:15px;line-height:1.6;margin:0 0 24px;">
          Hello <strong style="color:#fff;">${displayName}</strong>,<br/>
          Here is your OGENTI email verification code.
        </p>

        <!-- Code Box -->
        <div style="text-align:center;margin:32px 0;padding:28px 20px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:12px;">
          <p style="color:rgba(255,255,255,0.4);font-size:12px;text-transform:uppercase;letter-spacing:0.15em;margin:0 0 12px;">Verification Code</p>
          <div style="font-size:36px;font-weight:700;letter-spacing:8px;color:#fff;font-family:'Courier New',monospace;">
            ${code}
          </div>
        </div>

        <!-- Expiry Warning -->
        <p style="color:rgba(255,255,255,0.35);font-size:13px;text-align:center;margin:0 0 32px;">
          This code expires in <strong style="color:rgba(255,255,255,0.6);">10 minutes</strong>.
        </p>

        <!-- Divider -->
        <div style="height:1px;background:rgba(255,255,255,0.06);margin:24px 0;"></div>

        <!-- Footer -->
        <p style="color:rgba(255,255,255,0.2);font-size:11px;text-align:center;margin:0;">
          If you did not request this, please ignore this email.<br/>
          &copy; 2026 OGENTI, Inc.
        </p>
      </div>
    </body>
    </html>
    `;

    try {
      const transport = this.getTransporter();

      if (!config.smtp.user || !config.smtp.pass) {
        // Development mode: log the code
        logger.info(`========================================`);
        logger.info(`📧 VERIFICATION EMAIL (dev mode)`);
        logger.info(`   To: ${to}`);
        logger.info(`   Code: ${code}`);
        logger.info(`========================================`);
        return true;
      }

      await transport.sendMail({
        from: `"OGENTI" <${config.smtp.from}>`,
        to,
        subject,
        html,
      });

      logger.info(`Verification email sent to ${to}`);
      return true;
    } catch (error) {
      logger.error(`Failed to send verification email to ${to}:`, error);
      throw new Error(`Failed to send verification email: ${(error as Error).message}`);
    }
  }
}

export const emailService = new EmailService();
