const express = require('express');
const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { ListToolsRequestSchema, CallToolRequestSchema } = require('@modelcontextprotocol/sdk/types.js');
const imap = require('imap');
const { simpleParser } = require('mailparser');
const nodemailer = require('nodemailer');

const app = express();
app.use(express.json());

const IMAP_CONFIG = {
  user: process.env.IMAP_USER,
  password: process.env.IMAP_PASS,
  host: 'imap.163.com',
  port: 993,
  tls: true
};

const SMTP_CONFIG = {
  host: 'smtp.163.com',
  port: 465,
  secure: true,
  auth: { user: process.env.IMAP_USER, pass: process.env.SMTP_PASS }
};

const server = new Server({ name: 'email-server', version: '1.0.0' }, { capabilities: { tools: {} } });

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      { name: 'list_emails', description: '列出最近的邮件', inputSchema: { type: 'object', properties: {} } },
      { name: 'send_email', description: '发送邮件', inputSchema: { type: 'object', properties: { to: { type: 'string' }, subject: { type: 'string' }, body: { type: 'string' } }, required: ['to', 'subject', 'body'] } }
    ]
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  if (name === 'list_emails') {
    return new Promise((resolve, reject) => {
      const imapServer = new imap(IMAP_CONFIG);
      imapServer.on('ready', () => {
        imapServer.openBox('INBOX', false, (err, box) => {
          if (err) throw err;
          const f = imapServer.seq.fetch(`${box.messages.total - 4}:*`, { bodies: '' });
          const emails = [];
          f.on('message', (msg) => {
            msg.on('body', (stream) => {
              simpleParser(stream, (err, mail) => {
                if (err) throw err;
                emails.push({ from: mail.from.text, subject: mail.subject, date: mail.date });
              });
            });
          });
          f.on('end', () => { imapServer.end(); resolve({ content: [{ type: 'text', text: JSON.stringify(emails, null, 2) }] }); });
        });
      });
      imapServer.on('error', (err) => reject(err));
      imapServer.connect();
    });
  } else if (name === 'send_email') {
    const transporter = nodemailer.createTransport(SMTP_CONFIG);
    const info = await transporter.sendMail({ from: process.env.IMAP_USER, to: args.to, subject: args.subject, text: args.body });
    return { content: [{ type: 'text', text: `邮件发送成功: ${info.messageId}` }] };
  }
  throw new Error(`Unknown tool: ${name}`);
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
