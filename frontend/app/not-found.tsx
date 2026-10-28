import { ErrorSheet } from "@/components/ErrorSheet";

export default function NotFound() {
  return (
    <main className="min-h-screen bg-paper">
      <ErrorSheet
        code="404"
        stamp="Not found"
        title="There is no page at this address"
        text="The link may be mistyped, or the review may belong to another demo workspace. Each visitor gets a private copy of PayWise, so reviews are not shared between browsers."
      />
    </main>
  );
}
