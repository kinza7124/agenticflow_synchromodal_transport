import "./globals.css";

export const metadata = {
  title: "Synchromodal Control Tower Dashboard",
  description: "Agentic synchromodal hinterland freight transportation replanning system",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
