import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles/globals.css";

const container = document.getElementById("root");
if (!container) throw new Error("#root is missing from index.html");

// Runs are persisted server-side and immutable once complete, so a response is
// good for the life of the page. No refetch-on-focus surprises mid-demo.
const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: Infinity, refetchOnWindowFocus: false, retry: 1 } },
});

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
