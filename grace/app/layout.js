export const metadata = {
  title: "GRACE",
  description: "Write a script, tap create, it uploads to YouTube.",
  manifest: "/manifest.json",
  themeColor: "#060a08",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
        <link rel="apple-touch-icon" href="/icon.png" />
      </head>
      <body style={{ margin: 0, background: "#060a08", color: "#eafff2", fontFamily: "ui-monospace, 'Fira Code', monospace" }}>
        {children}
      </body>
    </html>
  );
}
