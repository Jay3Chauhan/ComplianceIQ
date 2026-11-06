import type { Metadata } from "next";
import { AdminLogin } from "@/components/admin/login-form";

export const metadata: Metadata = { title: "Admin sign-in", robots: { index: false } };

export default function AdminLoginPage() {
  return <AdminLogin />;
}
