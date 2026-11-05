export default function FeedbackButtons({ given, onRate }: {
  given: boolean; onRate: (rating: 1 | -1) => void;
}) {
  return (
    <section className="feedback card">
      <h3>Was this reply helpful?</h3>
      {given ? (
        <p className="muted">Thanks — feedback recorded.</p>
      ) : (
        <div className="feedback-actions">
          <button onClick={() => onRate(1)} data-testid="feedback-up">👍</button>
          <button onClick={() => onRate(-1)} data-testid="feedback-down">👎</button>
        </div>
      )}
    </section>
  );
}