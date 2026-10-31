export default function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-bad/30 bg-bad-bg px-4 py-3 text-bad">
      <p>{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-2 rounded-md bg-bad px-3 py-1 text-sm font-semibold text-white">
          Try again
        </button>
      )}
    </div>
  );
}
