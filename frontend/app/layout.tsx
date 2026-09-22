import { Inter, Sora } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { ThemeProvider } from "@/lib/theme";
import { Toaster } from "@/components/ui";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const sora = Sora({ subsets: ["latin"], variable: "--font-sora", weight: ["600", "700", "800"] });

export const metadata = {
  title: "Prism HR — Policy Assistant",
  description: "Ask HR policies in plain language. Cited, role-aware answers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} ${sora.variable} font-sans app-aurora`}>
        <ThemeProvider>
          <AuthProvider>
            <Toaster>{children}</Toaster>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
