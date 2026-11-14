import React from "react";
import { RouterProvider } from "react-router";
import { AppProviders } from "./app/providers";
import { createAppRouter } from "./app/router";

const router = createAppRouter();

export const App: React.FC = () => (
  <AppProviders>
    <RouterProvider router={router} />
  </AppProviders>
);

export default App;
