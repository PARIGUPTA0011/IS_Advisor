import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "./contexts/ThemeContext";
import { AnalysisPrefsProvider } from "./contexts/AnalysisPrefsContext";
import { AppLayout } from "./components/layout/AppLayout";
import { Dashboard } from "./pages/Dashboard";
import { Analyze } from "./pages/Analyze";
import { Results } from "./pages/Results";
import { Settings } from "./pages/Settings";

function App() {
  return (
    <ThemeProvider>
      <AnalysisPrefsProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<Dashboard />} />
              <Route path="analyze" element={<Analyze />} />
              <Route path="results" element={<Results />} />
              <Route path="settings" element={<Settings />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AnalysisPrefsProvider>
    </ThemeProvider>
  );
}

export default App;
