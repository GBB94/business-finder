import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/api"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Let public paths through
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Allow static assets and Next.js internals
  if (pathname.startsWith("/_next") || pathname.includes(".")) {
    return NextResponse.next();
  }

  // Check for session cookie
  const sessionId = request.cookies.get("session_id");
  if (!sessionId?.value) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
