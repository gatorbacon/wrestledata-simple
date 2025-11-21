import { createBrowserRouter, createRoutesFromElements, Route } from 'react-router-dom';
import App from './App'; // Import the main App component
import HomePage from './components/HomePage';
import WrestlerPage from './components/WrestlerPage';
import TeamPage from './components/TeamPage';
import WrestlerProfiles from './components/WrestlerProfiles';
import Rankings from './components/Rankings';
import RecruitTools from './components/RecruitTools';
import FantasyBrackets from './components/FantasyBrackets';

// Enable future flags
const routerConfig = {
  future: {
    v7_startTransition: true,
    v7_relativeSplatPath: true
  }
};

const router = createBrowserRouter(
  createRoutesFromElements(
    // Use App as the layout route
    <Route path="/" element={<App />}>
      {/* Nested Routes will render inside App's Outlet */}
      <Route index element={<HomePage />} /> {/* index=true makes this the default child route for "/" */}
      <Route path="test" element={<h2>Test Route Works!</h2>} />
      <Route path="wrestler/:careerId" element={<WrestlerPage />} />
      <Route path="team/:id" element={<TeamPage />} />
      <Route path="wrestlers" element={<WrestlerProfiles />} />
      <Route path="rankings" element={<Rankings />} />
      <Route path="recruit-tools" element={<RecruitTools />} />
      <Route path="fantasy-brackets" element={<FantasyBrackets />} />
    </Route>
  ),
  routerConfig
);

export default router; 