import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "./contexts/ThemeContext";
import { AnalysisPrefsProvider } from "./contexts/AnalysisPrefsContext";
import { AppLayout } from "./components/layout/AppLayout";
import { Dashboard } from "./pages/Dashboard";
import { Analyze } from "./pages/Analyze";
import { Results } from "./pages/Results";
import { Settings } from "./pages/Settings";
import { EntryPoint } from "./pages/EntryPoint";
import { About } from "./pages/About";
import TenderHealth from "./pages/TenderHealth";

function App() {
  return (
    <ThemeProvider>
      <AnalysisPrefsProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<Dashboard />} />
              <Route path="analyze" element={<Analyze />} />
              <Route path="tender-health" element={<TenderHealth />} />
              <Route path="results" element={<Results />} />
              <Route path="history" element={<EntryPoint />} />
              <Route path="settings" element={<Settings />} />
              <Route path="about" element={<About />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AnalysisPrefsProvider>
    </ThemeProvider>
  );
}

export default App;
