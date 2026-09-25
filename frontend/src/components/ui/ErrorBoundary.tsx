import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="card">
          <div className="state" role="alert">
            <div className="state__icon state__icon--error">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 8v4" />
                <path d="M12 16h.01" />
              </svg>
            </div>
            <div>
              <p className="state__title">Something went wrong</p>
              <p className="state__message">
                An unexpected error interrupted this view. Your data is safe —
                try again or choose another area from the navigation.
              </p>
              <div className="state__actions">
                <button
                  type="button"
                  className="btn btn--primary btn--sm"
                  onClick={() => this.setState({ error: null })}
                >
                  Try again
                </button>
              </div>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}