"use client";

import { useEffect } from "react";

import { ErrorSheet } from "@/components/ErrorSheet";

// Errors inside the app keep the header and footer, so the visitor can still navigate away.
export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <ErrorSheet
      code="500"
      stamp="Returned"
      title="This page hit a problem"
      text="Something went wrong while showing this page. Your work is saved on the server; trying again usually fixes it."
      reference={error.digest}
      action={
        <button type="button" className="btn-primary" onClick={reset}>
          Try again
        </button>
      }
    />
  );
}
