import { Navbar } from "../components/landing/Navbar";
import { Hero } from "../components/landing/Hero";
import { Features } from "../components/landing/Features";
import { ChatDemo } from "../components/landing/ChatDemo";
import { Footer } from "../components/landing/Footer";


export default function Home(){
    return(
        <div style={ {padding: '2rem'}} >
           <Navbar />
         <main>
          <Hero />
          <Features />
          <ChatDemo />
          <Footer />

         </main>
        </div>
    );
}