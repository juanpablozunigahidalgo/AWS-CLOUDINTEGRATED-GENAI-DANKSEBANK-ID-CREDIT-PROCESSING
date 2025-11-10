import { Routes, Route } from "react-router-dom";
import Header from "./components/Header";
import Home from "./Pages/Home";
import Clients from "./Pages/Clients";
import Verify from "./Pages/Verify";

export default function App() {
  return (
    <>
      <Header />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/clients" element={<Clients />} />
        <Route path="/verify" element={<Verify />} />
      </Routes>
    </>
  );
}
