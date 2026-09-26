import { NextRequest, NextResponse } from 'next/server';

const AUTH_COOKIE_NAME = 'nusaflow_token';

export function middleware(request: NextRequest) {
  const token = request.cookies.get(AUTH_COOKIE_NAME)?.value;
  const { pathname } = request.nextUrl;

  // The ONLY thing this middleware does: keep an unauthenticated browser
  // from loading the dashboard shell. /login and /signup are deliberately
  // NOT redirected to /dashboard when a token exists — the cookie is only
  // checked for presence here, not for *whose* token it is, so a visitor
  // who once clicked "Explore Demo" (7-day cookie) would otherwise get
  // bounced straight into the demo dashboard every time they tried to
  // sign up or log in to their own workspace. The auth pages themselves
  // detect an existing session client-side and offer a "continue" link
  // instead of forcing a redirect. See README "Authentication & Workspaces".
  if (pathname.startsWith('/dashboard') && !token) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('next', pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/dashboard/:path*'],
};
