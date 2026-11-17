# Global Rule: Modern Web Guidance Integration

Whenever developing, generating, or modifying Web applications, HTML, CSS, or Client-Side JavaScript:
1. **Always Follow Modern Web Guidance Best Practices**:
   - Utilize Core Web Vitals (CWV) optimizations, including resource preloading (`<link rel="preconnect">`, `<link rel="dns-prefetch">`, `fetchpriority="high"`).
   - Implement native modern CSS features (Container Queries, View Transitions, `content-visibility: auto` for layout and scroll optimization).
   - Enforce robust Web Security headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`).
   - Prevent XSS vulnerabilities by preferring safe DOM manipulation over unsanitized `innerHTML`.
2. **Ensure High-Fidelity Performance and Responsiveness**:
   - Minimize DOM layout thrashing and maintain smooth frame rates on mobile devices.
   - Use Baseline widely available web standards with graceful progressive degradation.
